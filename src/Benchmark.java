import java.io.*;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.ZonedDateTime;
import java.util.*;

/**
 * Đo thời gian MergeCutoff theo thiết kế đã chốt.
 *
 * Chạy (KHÔNG có -ea), từ thư mục cutoff-experiment:
 *   java -Xms2g -Xmx2g -XX:+UseSerialGC -XX:+AlwaysPreTouch -cp build Benchmark --fork 1 [--resume]
 *   java -Xms2g -Xmx2g -XX:+UseSerialGC -XX:+AlwaysPreTouch -cp build Benchmark --pilot
 *   tùy chọn: --data <dir> (mặc định data), --results <dir> (mặc định results)
 *
 * Cách ly: JVM này chỉ sort Integer[] bằng MergeCutoff. Không tham chiếu CorrectnessTest, Key, Item,
 * MergeCutoffCounted; không sort Comparable nào khác (thứ tự CUTOFF / bộ dữ liệu xáo trên int[]).
 *
 * Thủ tục một lần đo:
 *   System.gc() -> clone K bản -> gcBefore -> t0 -> sort K lần -> t1 -> gcAfter
 *   ngoài vùng đo: isSorted trên bản đầu (sai thì dừng), cộng vào sink.
 *   time_ns = round((t1 - t0) / K), timestamp_ns = t0.
 *
 * Lô K (cố định cho mọi CUTOFF của một bộ, để giữ ghép cặp):
 *   K = clamp(ceil(TARGET_BATCH_NS / t_min), 1, K_MAX), t_min = thời gian/sort nhỏ nhất trên lưới
 *   ở vòng warm-up cuối của bộ đó. TARGET_BATCH_NS = 2 ms.
 *
 * Seed:
 *   thứ tự bộ dữ liệu : new Random(1000 + fork), Knuth shuffle
 *   thứ tự CUTOFF     : new Random(mix64((fork*1e8 + dataset_seed)*1e4 + t)),
 *                       t = trial (1..R); warm-up bộ dữ liệu vòng r: t = 1000 + r;
 *                       warm-up JVM vòng r: dataset_seed = 0, t = 5000 + r
 */
public final class Benchmark
{
   // ------------------------------------------------------------------ thiết kế (đã chốt)

   static final int[] FULL_GRID = fullGrid();                                    // 1..32, 40, 48, 64
   static final int[] SPARSE_GRID = {1, 2, 4, 6, 8, 10, 12, 16, 20, 24, 32, 48, 64};
   static final int DATASET_WARMUP_ROUNDS = 3;
   static final long TARGET_BATCH_NS = 2_000_000L;
   static final int K_MAX = 1000;
   static final int JVM_WARMUP_N = 1 << 16;
   static final long JVM_WARMUP_SEED = 777L;          // không có dạng 10^7*id + N, nên không trùng file trong data/
   static final int JVM_WARMUP_MIN_ROUNDS = 6, JVM_WARMUP_MAX_ROUNDS = 30;
   static final double JVM_WARMUP_TOL = 0.02;         // |mean(3 vòng cuối) / mean(3 vòng trước) - 1| < 2%
   static final int PILOT_R = 2;

   static final String RAW_HEADER =
      "fork,run_order,timestamp_ns,trial,distribution,N,seed,cutoff,batch_k,time_ns,gc_during_run";
   static final String WARMUP_HEADER = "fork,distribution,N,cutoff,warmup_iter,time_ns";

   static int[] fullGrid()
   {
      int[] g = new int[35];
      for (int i = 0; i < 32; i++) g[i] = i + 1;
      g[32] = 40; g[33] = 48; g[34] = 64;
      return g;
   }

   record DS(String dist, int n, long seed, String file, String sha)
   {
      int scale()  { return Integer.highestOneBit(n); }
      String key() { return dist + "," + n; }
   }

   static int[] gridFor(String dist) { return dist.equals("random") ? FULL_GRID : SPARSE_GRID; }

   static int repsFor(DS ds)
   {
      if (ds.dist().equals("random")) return ds.scale() <= (1 << 16) ? 10 : 5;
      return 5;
   }

   // ------------------------------------------------------------------ trạng thái

   static int fork;
   static boolean pilot;
   static int fixedK = -1;
   static int onlyScale = -1;
   static int limitDatasets = -1;
   static long sink = 0;
   static long runOrder = 0;
   static long gcFlagged = 0;
   static long lastT0;
   static boolean lastGc;
   static List<GarbageCollectorMXBean> gcs;
   static Path envFile;

   // ------------------------------------------------------------------ đo

   static long gcCount()
   {
      long s = 0;
      for (GarbageCollectorMXBean b : gcs)
      {
         long c = b.getCollectionCount();
         if (c > 0) s += c;
      }
      return s;
   }

   static boolean isSorted(Integer[] a)
   {
      for (int i = 1; i < a.length; i++)
         if (a[i].intValue() < a[i - 1].intValue()) return false;
      return true;
   }

   /** Một lần đo; trả về thời gian mỗi lần sort (ns). Ghi t0 vào lastT0, cờ GC vào lastGc. */
   static long measure(Integer[] base, int cutoff, int k)
   {
      System.gc();
      Integer[][] copies = new Integer[k][];
      for (int i = 0; i < k; i++) copies[i] = base.clone();
      long gc0 = gcCount();
      long t0 = System.nanoTime();
      for (int i = 0; i < k; i++) MergeCutoff.sort(copies[i], cutoff);
      long t1 = System.nanoTime();
      long gc1 = gcCount();

      Integer[] a = copies[0];
      if (!isSorted(a))
         fatal("output NOT sorted: N=" + a.length + " cutoff=" + cutoff);
      if (a.length > 0) sink += a[0] + 31L * a[a.length / 2] + 961L * a[a.length - 1];
      lastT0 = t0;
      lastGc = gc1 != gc0;
      return Math.round((t1 - t0) / (double) k);
   }

   static int kFor(long perSortNs)
   {
      if (perSortNs <= 0) return K_MAX;
      long k = (TARGET_BATCH_NS + perSortNs - 1) / perSortNs;
      return (int) Math.max(1, Math.min(K_MAX, k));
   }

   static long trialSeed(long dsSeed, int t)
   {
      return DataGenerator.mix64((fork * 100_000_000L + dsSeed) * 10_000L + t);
   }

   static int[] shuffled(int[] g, long seed)
   {
      int[] a = g.clone();
      Random r = new Random(seed);
      for (int i = 0; i < a.length; i++)          // Knuth shuffle (bài giảng)
      {
         int j = r.nextInt(i + 1);
         int t = a[i]; a[i] = a[j]; a[j] = t;
      }
      return a;
   }

   static Integer[] box(int[] v)
   {
      Integer[] a = new Integer[v.length];
      for (int i = 0; i < v.length; i++) a[i] = Integer.valueOf(v[i]);
      return a;
   }

   static int[] decode(byte[] b)
   {
      int[] a = new int[b.length / 4];
      ByteBuffer.wrap(b).order(ByteOrder.LITTLE_ENDIAN).asIntBuffer().get(a);
      return a;
   }

   // ------------------------------------------------------------------ manifest

   static List<DS> readManifest(Path dataDir) throws IOException
   {
      List<String> lines = Files.readAllLines(dataDir.resolve("manifest.csv"), StandardCharsets.UTF_8);
      if (lines.isEmpty() || !lines.get(0).equals(DataGenerator.MANIFEST_HEADER))
         fatal("bad manifest header in " + dataDir.resolve("manifest.csv"));
      List<DS> out = new ArrayList<>();
      for (int i = 1; i < lines.size(); i++)
      {
         String[] c = lines.get(i).split(",");
         DS ds = new DS(c[0], Integer.parseInt(c[1]), Long.parseLong(c[2]), c[3], c[4]);
         boolean ok = switch (ds.dist())
         {
            case "random" -> ds.scale() == (1 << 12) || ds.scale() == (1 << 16) || ds.scale() == (1 << 19);
            case "sorted", "reversed", "nearly_sorted", "few_distinct" -> ds.scale() == (1 << 16);
            default -> false;
         };
         if (!ok) fatal("manifest row does not match the design: " + lines.get(i));
         out.add(ds);
      }
      return out;
   }

   /** Pilot: random j = 0, 12, 23 mỗi thang; phân bố khác j = 0, 23. */
   static List<DS> pilotSubset(List<DS> all)
   {
      Map<String, List<DS>> groups = new LinkedHashMap<>();
      for (DS ds : all) groups.computeIfAbsent(ds.dist() + "@" + ds.scale(), g -> new ArrayList<>()).add(ds);
      List<DS> out = new ArrayList<>();
      for (List<DS> g : groups.values())
      {
         int[] pick = g.get(0).dist().equals("random") ? new int[]{0, 12, 23} : new int[]{0, 23};
         for (int j : pick) if (j < g.size()) out.add(g.get(j));
      }
      return out;
   }

   // ------------------------------------------------------------------ resume

   /** Giữ các bộ đã đủ dòng; xóa dòng của bộ dở dang (raw và warm-up); đặt runOrder tiếp nối. */
   static Set<String> resumeScan(Path raw, Path warm, Map<String, Integer> expected) throws IOException
   {
      Set<String> complete = new HashSet<>();
      if (!Files.exists(raw)) return complete;
      List<String> lines = Files.readAllLines(raw, StandardCharsets.UTF_8);
      if (lines.isEmpty()) return complete;
      if (!lines.get(0).equals(RAW_HEADER)) fatal("bad header in " + raw);
      Map<String, Integer> count = new HashMap<>();
      for (int i = 1; i < lines.size(); i++)
      {
         String[] c = lines.get(i).split(",");
         count.merge(c[4] + "," + c[5], 1, Integer::sum);
      }
      for (Map.Entry<String, Integer> e : count.entrySet())
         if (e.getValue().equals(expected.get(e.getKey()))) complete.add(e.getKey());

      List<String> keptRaw = new ArrayList<>(List.of(RAW_HEADER));
      for (int i = 1; i < lines.size(); i++)
      {
         String[] c = lines.get(i).split(",");
         if (complete.contains(c[4] + "," + c[5]))
         {
            keptRaw.add(lines.get(i));
            runOrder = Math.max(runOrder, Long.parseLong(c[1]));
         }
      }
      if (keptRaw.size() != lines.size())
      {
         System.out.printf("resume: dropping %d rows of incomplete datasets from %s%n",
                           lines.size() - keptRaw.size(), raw);
         writeLines(raw, keptRaw);
      }
      if (Files.exists(warm))
      {
         List<String> wl = Files.readAllLines(warm, StandardCharsets.UTF_8);
         List<String> keptW = new ArrayList<>(List.of(WARMUP_HEADER));
         for (int i = 1; i < wl.size(); i++)
         {
            String[] c = wl.get(i).split(",");
            if (c[1].equals("jvm_warmup") || complete.contains(c[1] + "," + c[2])) keptW.add(wl.get(i));
         }
         if (keptW.size() != wl.size()) writeLines(warm, keptW);
      }
      return complete;
   }

   static void writeLines(Path p, List<String> lines) throws IOException
   {
      Path tmp = p.resolveSibling(p.getFileName() + ".tmp");
      try (BufferedWriter w = Files.newBufferedWriter(tmp, StandardCharsets.UTF_8))
      {
         for (String l : lines) { w.write(l); w.write('\n'); }
      }
      Files.move(tmp, p, StandardCopyOption.REPLACE_EXISTING);
   }

   static BufferedWriter openAppend(Path p, String header) throws IOException
   {
      boolean fresh = !Files.exists(p) || Files.size(p) == 0;
      BufferedWriter w = Files.newBufferedWriter(p, StandardCharsets.UTF_8,
                                                 StandardOpenOption.CREATE, StandardOpenOption.APPEND);
      if (fresh) { w.write(header); w.write('\n'); w.flush(); }
      return w;
   }

   // ------------------------------------------------------------------ env

   static void env(String s)
   {
      try { Files.writeString(envFile, s + "\n", StandardCharsets.UTF_8,
                              StandardOpenOption.CREATE, StandardOpenOption.APPEND); }
      catch (IOException e) { throw new UncheckedIOException(e); }
   }

   static void writeEnvHeader(boolean resumed, List<DS> order)
   {
      com.sun.management.OperatingSystemMXBean os =
         (com.sun.management.OperatingSystemMXBean) ManagementFactory.getOperatingSystemMXBean();
      StringBuilder sb = new StringBuilder();
      sb.append("=== session start (").append(resumed ? "resumed" : "fresh").append(") ===\n");
      sb.append("start_time=").append(ZonedDateTime.now()).append('\n');
      sb.append("mode=").append(pilot ? "pilot" : "full").append('\n');
      sb.append("fork=").append(fork).append('\n');
      if (fixedK > 0) sb.append("fixed_k=").append(fixedK).append('\n');
      if (onlyScale > 0) sb.append("only_scale=").append(onlyScale).append('\n');
      if (limitDatasets > 0) sb.append("limit_datasets=").append(limitDatasets).append('\n');
      for (String k : new String[]{"java.version", "java.vm.name", "java.vm.version", "java.vendor",
                                   "os.name", "os.version", "os.arch"})
         sb.append(k).append('=').append(System.getProperty(k)).append('\n');
      sb.append("availableProcessors=").append(Runtime.getRuntime().availableProcessors()).append('\n');
      sb.append("maxMemory=").append(Runtime.getRuntime().maxMemory()).append('\n');
      sb.append("physical_memory_total=").append(os.getTotalMemorySize()).append('\n');
      sb.append("physical_memory_free_at_start=").append(os.getFreeMemorySize()).append('\n');
      sb.append("jvm_input_arguments=").append(ManagementFactory.getRuntimeMXBean().getInputArguments()).append('\n');
      List<String> names = new ArrayList<>();
      for (GarbageCollectorMXBean b : gcs) names.add(b.getName());
      sb.append("gc_collectors=").append(names).append('\n');
      sb.append("assertions=disabled\n");
      sb.append("target_batch_ns=").append(TARGET_BATCH_NS).append(", k_max=").append(K_MAX)
        .append(", dataset_warmup_rounds=").append(DATASET_WARMUP_ROUNDS).append('\n');
      sb.append("dataset_order_seed=").append(1000 + fork).append(" (java.util.Random, Knuth shuffle)\n");
      sb.append("cutoff_order_seed=mix64((fork*1e8 + dataset_seed)*1e4 + t); t=trial | 1000+warmup_round | jvm: seed 0, 5000+round\n");
      sb.append("dataset_order (index distribution N seed):\n");
      for (int i = 0; i < order.size(); i++)
         sb.append("  ").append(i + 1).append(' ').append(order.get(i).dist()).append(' ')
           .append(order.get(i).n()).append(' ').append(order.get(i).seed()).append('\n');
      env(sb.toString().stripTrailing());
   }

   // ------------------------------------------------------------------ warm-up JVM

   static double jvmWarmup(BufferedWriter warmW) throws IOException
   {
      long start = System.nanoTime();
      Integer[] base = box(DataGenerator.generate("random", JVM_WARMUP_N, JVM_WARMUP_SEED));
      StringBuilder rows = new StringBuilder();
      List<Double> totals = new ArrayList<>();
      boolean converged = false;
      for (int r = 1; r <= JVM_WARMUP_MAX_ROUNDS; r++)
      {
         double tot = 0;
         for (int c : shuffled(FULL_GRID, trialSeed(0, 5000 + r)))
         {
            long t = measure(base, c, fixedK > 0 ? fixedK : 1);
            tot += t;
            rows.append(fork).append(",jvm_warmup,").append(JVM_WARMUP_N).append(',').append(c).append(',')
                .append(r).append(',').append(t).append('\n');
         }
         totals.add(tot);
         if (r >= JVM_WARMUP_MIN_ROUNDS)
         {
            double last = (totals.get(r - 1) + totals.get(r - 2) + totals.get(r - 3)) / 3;
            double prev = (totals.get(r - 4) + totals.get(r - 5) + totals.get(r - 6)) / 3;
            if (Math.abs(last / prev - 1) < JVM_WARMUP_TOL) { converged = true; break; }
         }
      }
      warmW.write(rows.toString());
      warmW.flush();
      double sec = (System.nanoTime() - start) / 1e9;
      StringBuilder t = new StringBuilder();
      for (double x : totals) t.append(String.format(Locale.ROOT, "%.1f ", x / 1e6));
      env(String.format(Locale.ROOT, "jvm_warmup: N=%d seed=%d rounds=%d converged=%b time=%.1fs round_totals_ms=[%s]",
                        JVM_WARMUP_N, JVM_WARMUP_SEED, totals.size(), converged, sec, t.toString().trim()));
      System.out.printf(Locale.ROOT, "[fork %d] JVM warm-up: %d rounds, converged=%b, %.1f s%n",
                        fork, totals.size(), converged, sec);
      return sec;
   }

   // ------------------------------------------------------------------ một bộ dữ liệu

   /** @return {load_s, warmup_s, measure_s, K} */
   static double[] runDataset(Path dataDir, DS ds, BufferedWriter rawW, BufferedWriter warmW) throws IOException
   {
      long tl0 = System.nanoTime();
      byte[] bytes = Files.readAllBytes(dataDir.resolve(ds.file()));
      if (!DataGenerator.sha256(bytes).equals(ds.sha())) fatal("sha256 mismatch: " + ds.file());
      int[] v = decode(bytes);
      if (v.length != ds.n()) fatal("length mismatch: " + ds.file());
      Integer[] base = box(v);            // box MỘT lần; mọi lần đo clone từ base
      bytes = null; v = null;
      long tl1 = System.nanoTime();

      int[] grid = gridFor(ds.dist());
      int reps = pilot ? PILOT_R : repsFor(ds);

      int kw, k;
      if (fixedK > 0)
      {
         kw = fixedK;
         k = fixedK;
      }
      else
      {
         // dò sơ bộ để chọn K cho warm-up (không ghi lại)
         long probe = Long.MAX_VALUE;
         for (int i = 0; i < 3; i++) probe = Math.min(probe, measure(base, grid[grid.length / 2], 1));
         kw = kFor(probe);
         k = -1;
      }

      StringBuilder warmRows = new StringBuilder();
      long minLast = Long.MAX_VALUE;
      for (int r = 1; r <= DATASET_WARMUP_ROUNDS; r++)
         for (int c : shuffled(grid, trialSeed(ds.seed(), 1000 + r)))
         {
            long t = measure(base, c, kw);
            warmRows.append(fork).append(',').append(ds.dist()).append(',').append(ds.n()).append(',')
                    .append(c).append(',').append(r).append(',').append(t).append('\n');
            if (r == DATASET_WARMUP_ROUNDS) minLast = Math.min(minLast, t);
         }
      if (fixedK <= 0) k = kFor(minLast);              // K cố định cho mọi CUTOFF của bộ này
      long tw1 = System.nanoTime();

      StringBuilder rawRows = new StringBuilder();
      long flagged = 0;
      for (int trial = 1; trial <= reps; trial++)
         for (int c : shuffled(grid, trialSeed(ds.seed(), trial)))
         {
            long t = measure(base, c, k);
            runOrder++;
            if (lastGc) flagged++;
            rawRows.append(fork).append(',').append(runOrder).append(',').append(lastT0).append(',')
                   .append(trial).append(',').append(ds.dist()).append(',').append(ds.n()).append(',')
                   .append(ds.seed()).append(',').append(c).append(',').append(k).append(',')
                   .append(t).append(',').append(lastGc).append('\n');
         }
      long tm1 = System.nanoTime();
      gcFlagged += flagged;

      warmW.write(warmRows.toString()); warmW.flush();
      rawW.write(rawRows.toString());   rawW.flush();       // raw ghi sau cùng: --resume dựa vào raw

      double[] t = {(tl1 - tl0) / 1e9, (tw1 - tl1) / 1e9, (tm1 - tw1) / 1e9, k};
      env(String.format(Locale.ROOT,
          "dataset %s N=%d seed=%d R=%d grid=%d K_warmup=%d K=%d load=%.2fs warmup=%.1fs measure=%.1fs gc_flagged=%d",
          ds.dist(), ds.n(), ds.seed(), reps, grid.length, kw, k, t[0], t[1], t[2], flagged));
      return t;
   }

   // ------------------------------------------------------------------ main

   static void fatal(String msg)
   {
      System.err.println("FATAL: " + msg);
      try { if (envFile != null) env("FATAL: " + msg); } catch (Exception ignored) {}
      System.exit(3);
   }

   static boolean assertionsEnabled()
   {
      boolean ea = false;
      assert ea = true;
      return ea || MergeCutoff.class.desiredAssertionStatus();
   }

   static double units(DS ds, int measurements)
   {
      return measurements * (double) ds.n() * (Math.log(ds.n()) / Math.log(2));
   }

   static int parseScale(String s)
   {
      if (s.startsWith("2^")) return 1 << Integer.parseInt(s.substring(2));
      return Integer.parseInt(s);
   }

   public static void main(String[] args) throws IOException
   {
      if (assertionsEnabled())
      {
         System.err.println("ERROR: assertions are enabled. Benchmark must run WITHOUT -ea "
                            + "(the asserts in MergeCutoff.merge would be timed).");
         System.exit(2);
      }
      Path dataDir = Paths.get("data"), resultsDir = Paths.get("results");
      boolean resume = false;
      fork = 0;
      for (int i = 0; i < args.length; i++)
      {
         switch (args[i])
         {
            case "--fork"           -> fork = Integer.parseInt(args[++i]);
            case "--pilot"          -> pilot = true;
            case "--resume"         -> resume = true;
            case "--data"           -> dataDir = Paths.get(args[++i]);
            case "--results"        -> resultsDir = Paths.get(args[++i]);
            case "--fixed-k"        -> fixedK = Integer.parseInt(args[++i]);
            case "--only-scale"     -> onlyScale = parseScale(args[++i]);
            case "--limit-datasets" -> limitDatasets = Integer.parseInt(args[++i]);
            default -> { System.err.println("unknown argument: " + args[i]); System.exit(2); }
         }
      }
      if (pilot)
      {
         if (fork == 0) fork = 1;
         resume = false;
         resultsDir = resultsDir.resolve("pilot");
      }
      if (fork < 1 || fork > 3) { System.err.println("--fork must be 1..3"); System.exit(2); }

      gcs = ManagementFactory.getGarbageCollectorMXBeans();
      Files.createDirectories(resultsDir);
      Path raw  = resultsDir.resolve("raw_fork" + fork + ".csv");
      Path warm = resultsDir.resolve("warmup_fork" + fork + ".csv");
      Path env  = resultsDir.resolve("env_fork" + fork + ".txt");

      List<DS> all = readManifest(dataDir);
      List<DS> chosen = pilot ? pilotSubset(all) : all;
      if (onlyScale > 0)
      {
         List<DS> filtered = new ArrayList<>();
         for (DS ds : chosen)
            if (ds.dist().equals("random") && ds.scale() == onlyScale) filtered.add(ds);
         chosen = filtered;
      }
      List<DS> order = new ArrayList<>(chosen);
      Random ro = new Random(1000 + fork);
      for (int i = 0; i < order.size(); i++)                  // Knuth shuffle thứ tự bộ dữ liệu
      {
         int j = ro.nextInt(i + 1);
         DS t = order.get(i); order.set(i, order.get(j)); order.set(j, t);
      }
      if (limitDatasets > 0 && limitDatasets < order.size())
      {
         order = new ArrayList<>(order.subList(0, limitDatasets));
      }

      Map<String, Integer> expected = new HashMap<>();
      for (DS ds : order) expected.put(ds.key(), (pilot ? PILOT_R : repsFor(ds)) * gridFor(ds.dist()).length);

      Set<String> done = new HashSet<>();
      if (pilot)
      {
         for (Path p : new Path[]{raw, warm, env}) Files.deleteIfExists(p);
      }
      else if (resume)
      {
         done = resumeScan(raw, warm, expected);
      }
      else if (Files.exists(raw) && Files.size(raw) > RAW_HEADER.length() + 1)
      {
         fatal(raw + " already has data; use --resume or delete it");
      }
      else
      {
         for (Path p : new Path[]{raw, warm, env}) Files.deleteIfExists(p);
      }

      envFile = env;                       // chỉ ghi env sau khi đã qua các kiểm tra trên
      writeEnvHeader(resume, order);
      if (resume) env("resume: " + done.size() + " datasets already complete, run_order continues after " + runOrder);

      long tStart = System.nanoTime();
      double totalUnits = 0, doneUnits = 0;
      for (DS ds : order)
         if (!done.contains(ds.key()))
            totalUnits += units(ds, (DATASET_WARMUP_ROUNDS + expected.get(ds.key()) / gridFor(ds.dist()).length)
                                    * gridFor(ds.dist()).length);

      Map<String, double[]> pilotStats = new LinkedHashMap<>();   // dist@scale -> {sec, units, load_s, N}
      double jvmWarmSec;
      try (BufferedWriter rawW = openAppend(raw, RAW_HEADER); BufferedWriter warmW = openAppend(warm, WARMUP_HEADER))
      {
         jvmWarmSec = jvmWarmup(warmW);
         long tLoop = System.nanoTime();           // ETA chỉ tính từ sau warm-up JVM
         int idx = 0;
         for (DS ds : order)
         {
            idx++;
            if (done.contains(ds.key())) continue;
            double[] t = runDataset(dataDir, ds, rawW, warmW);
            int g = gridFor(ds.dist()).length;
            int reps = expected.get(ds.key()) / g;
            double u = units(ds, (DATASET_WARMUP_ROUNDS + reps) * g);
            doneUnits += u;
            double el = (System.nanoTime() - tStart) / 1e9;
            double eta = (System.nanoTime() - tLoop) / 1e9 / doneUnits * (totalUnits - doneUnits);
            System.out.printf(Locale.ROOT, "[fork %d] %3d/%d %-13s N=%7d K=%3d  warm %6.1fs  meas %6.1fs | elapsed %s, ETA %s%n",
                              fork, idx, order.size(), ds.dist(), ds.n(), (int) t[3], t[1], t[2], hms(el), hms(eta));
            if (pilot)
            {
               double[] s = pilotStats.computeIfAbsent(group(ds), x -> new double[4]);
               s[0] += t[1] + t[2]; s[1] += u; s[2] += t[0]; s[3] += ds.n();
            }
         }
      }
      double total = (System.nanoTime() - tStart) / 1e9;
      env(String.format(Locale.ROOT, "end_time=%s elapsed=%s gc_during_run_flagged=%d sink=%d",
                        ZonedDateTime.now(), hms(total), gcFlagged, sink));
      System.out.printf(Locale.ROOT, "[fork %d] done in %s, gc_during_run flagged: %d, sink=%d%n",
                        fork, hms(total), gcFlagged, sink);

      if (pilot) printEstimate(all, pilotStats, jvmWarmSec, resultsDir);
   }

   static String group(DS ds) { return ds.dist() + "@2^" + Integer.numberOfTrailingZeros(ds.scale()); }

   static String hms(double sec)
   {
      long s = Math.round(sec);
      return String.format(Locale.ROOT, "%d:%02d:%02d", s / 3600, (s % 3600) / 60, s % 60);
   }

   /** Ước lượng lượt đầy đủ 3 fork: thời gian / (số lần đo * N lgN) theo từng (phân bố, thang). */
   static void printEstimate(List<DS> all, Map<String, double[]> stats, double jvmWarmSec, Path dir) throws IOException
   {
      double loadSec = 0, loadN = 0;
      for (double[] s : stats.values()) { loadSec += s[2]; loadN += s[3]; }
      double loadRate = loadSec / loadN;

      Map<String, double[]> est = new LinkedHashMap<>();    // dist@scale -> {datasets, measurements, warm_s, meas_s}
      double perFork = jvmWarmSec;
      for (DS ds : all)
      {
         String key = group(ds);
         double[] s = stats.get(key);
         if (s == null) continue;
         double rate = s[0] / s[1];
         int g = gridFor(ds.dist()).length, reps = repsFor(ds);
         double warmS = rate * units(ds, DATASET_WARMUP_ROUNDS * g);
         double measS = rate * units(ds, reps * g);
         double[] e = est.computeIfAbsent(key, x -> new double[4]);
         e[0]++; e[1] += reps * g; e[2] += warmS; e[3] += measS;
         perFork += warmS + measS + loadRate * ds.n();
      }
      StringBuilder sb = new StringBuilder();
      sb.append("=== Estimate for the FULL run (from this pilot) ===\n");
      sb.append(String.format(Locale.ROOT, "%-22s %8s %13s %15s %15s%n",
                              "distribution@scale", "datasets", "measurements", "warm-up [min]", "measure [min]"));
      double w = 0, m = 0;
      for (Map.Entry<String, double[]> e : est.entrySet())
      {
         double[] v = e.getValue();
         String label = e.getKey();
         sb.append(String.format(Locale.ROOT, "%-22s %8d %13d %15.1f %15.1f%n",
                                 label, (int) v[0], (int) v[1], v[2] / 60, v[3] / 60));
         w += v[2]; m += v[3];
      }
      sb.append(String.format(Locale.ROOT, "JVM warm-up per fork   : %.1f min%n", jvmWarmSec / 60));
      sb.append(String.format(Locale.ROOT, "per fork               : %s  (dataset warm-up %.0f%%, measurement %.0f%%)%n",
                              hms(perFork), 100 * w / (perFork), 100 * m / (perFork)));
      sb.append(String.format(Locale.ROOT, "3 forks (Benchmark)    : %s%n", hms(3 * perFork)));
      sb.append("(excludes compile, CorrectnessTest, DataGenerator --verify, CountRunner)\n");
      System.out.print(sb);
      Files.writeString(dir.resolve("estimate.txt"), sb.toString(), StandardCharsets.UTF_8);
   }
}
