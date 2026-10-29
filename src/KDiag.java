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
 * KDiag – Công cụ chẩn đoán sai lệch do lô batch_k (T02c Phần B).
 *
 * Đo thời gian một lần sắp với các giá trị K cố định độc lập:
 *   - N thang 2^12 (j = 0, 5, 10, 15, 20, 23): K in {1, 2, 4, 8}
 *   - N thang 2^16 (j = 0, 12): K in {1, 2}
 *   - CUTOFF in {1, 7, 10, 30}
 *   - 20 trials mỗi (N, c, K), thứ tự (c, K) xáo trộn tất định mỗi trial.
 *
 * Chạy:
 *   java -Xms2g -Xmx2g -XX:+UseSerialGC -XX:+AlwaysPreTouch -cp build KDiag --fork 1 [--smoke]
 */
public final class KDiag
{
   static final int[] CUTOFFS = {1, 7, 10, 30};
   static final int[] K_SCALE_12 = {1, 2, 4, 8};
   static final int[] K_SCALE_16 = {1, 2};

   static final int[] J_SCALE_12 = {0, 5, 10, 15, 20, 23};
   static final int[] J_SCALE_16 = {0, 12};

   static final int DATASET_WARMUP_ROUNDS = 3;
   static final int JVM_WARMUP_N = 1 << 16;
   static final long JVM_WARMUP_SEED = 777L;
   static final int JVM_WARMUP_MIN_ROUNDS = 6, JVM_WARMUP_MAX_ROUNDS = 20;
   static final double JVM_WARMUP_TOL = 0.02;

   static final String RAW_HEADER = "fork,run_order,trial,N,seed,cutoff,k,time_ns,gc_during_run";

   record CK(int cutoff, int k) {}

   record DS(String dist, int n, long seed, String file, String sha)
   {
      int scale() { return Integer.highestOneBit(n); }
   }

   // ------------------------------------------------------------------ trạng thái
   static int fork = 1;
   static int trials = 20;
   static boolean smoke = false;
   static long sink = 0;
   static long runOrder = 0;
   static long gcFlagged = 0;
   static boolean lastGc;
   static List<GarbageCollectorMXBean> gcs;

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

   /** Đo thời gian một lần sắp với lô k cố định; trả về round((t1 - t0) / k) ns. */
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
         throw new IllegalStateException("FATAL: output NOT sorted: N=" + a.length + " cutoff=" + cutoff);
      if (a.length > 0) sink += a[0] + 31L * a[a.length / 2] + 961L * a[a.length - 1];

      lastGc = gc1 != gc0;
      return Math.round((t1 - t0) / (double) k);
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

   static List<DS> readTargetDatasets(Path dataDir, boolean smokeMode) throws IOException
   {
      List<String> lines = Files.readAllLines(dataDir.resolve("manifest.csv"), StandardCharsets.UTF_8);
      List<DS> rnd12 = new ArrayList<>();
      List<DS> rnd16 = new ArrayList<>();

      for (int i = 1; i < lines.size(); i++)
      {
         String[] c = lines.get(i).split(",");
         if (!c[0].equals("random")) continue;
         DS ds = new DS(c[0], Integer.parseInt(c[1]), Long.parseLong(c[2]), c[3], c[4]);
         if (ds.scale() == (1 << 12)) rnd12.add(ds);
         else if (ds.scale() == (1 << 16)) rnd16.add(ds);
      }
      rnd12.sort(Comparator.comparingInt(DS::n));
      rnd16.sort(Comparator.comparingInt(DS::n));

      List<DS> out = new ArrayList<>();
      if (smokeMode)
      {
         // Smoke test: 1 N (j = 0 của thang 2^12)
         out.add(rnd12.get(0));
      }
      else
      {
         for (int j : J_SCALE_12) if (j < rnd12.size()) out.add(rnd12.get(j));
         for (int j : J_SCALE_16) if (j < rnd16.size()) out.add(rnd16.get(j));
      }
      return out;
   }

   static List<CK> getPairsForN(int n)
   {
      int[] kVals = (n < 10000) ? K_SCALE_12 : K_SCALE_16;
      List<CK> list = new ArrayList<>();
      for (int c : CUTOFFS)
         for (int k : kVals)
            list.add(new CK(c, k));
      return list;
   }

   static void shufflePairs(List<CK> list, long seed)
   {
      Random r = new Random(seed);
      for (int i = 0; i < list.size(); i++)
      {
         int j = r.nextInt(i + 1);
         CK tmp = list.get(i);
         list.set(i, list.get(j));
         list.set(j, tmp);
      }
   }

   // ------------------------------------------------------------------ JVM warm-up
   static void jvmWarmup()
   {
      System.out.printf(Locale.ROOT, "[fork %d] Khởi động JVM warm-up...%n", fork);
      long t0 = System.nanoTime();
      Integer[] base = box(DataGenerator.generate("random", JVM_WARMUP_N, JVM_WARMUP_SEED));
      int maxR = smoke ? 3 : JVM_WARMUP_MAX_ROUNDS;
      int minR = JVM_WARMUP_MIN_ROUNDS;

      List<Double> totals = new ArrayList<>();
      boolean converged = false;
      for (int r = 1; r <= maxR; r++)
      {
         double tot = 0;
         List<CK> pairs = new ArrayList<>();
         for (int c : CUTOFFS) pairs.add(new CK(c, 1));
         shufflePairs(pairs, DataGenerator.mix64(5000L + r));
         for (CK ck : pairs)
         {
            long t = measure(base, ck.cutoff, ck.k);
            tot += t;
         }
         totals.add(tot);
         if (!smoke && r >= minR)
         {
            double last = (totals.get(r - 1) + totals.get(r - 2) + totals.get(r - 3)) / 3.0;
            double prev = (totals.get(r - 4) + totals.get(r - 5) + totals.get(r - 6)) / 3.0;
            if (Math.abs(last / prev - 1) < JVM_WARMUP_TOL) { converged = true; break; }
         }
      }
      double sec = (System.nanoTime() - t0) / 1e9;
      System.out.printf(Locale.ROOT, "[fork %d] JVM warm-up xong: %d rounds, hội tụ=%b, %.1f s%n",
                        fork, totals.size(), converged, sec);
   }

   // ------------------------------------------------------------------ main
   public static void main(String[] args) throws IOException
   {
      Path dataDir = Paths.get("data");
      Path resultsDir = Paths.get("results_kdiag");

      for (int i = 0; i < args.length; i++)
      {
         switch (args[i])
         {
            case "--fork"    -> fork = Integer.parseInt(args[++i]);
            case "--results" -> resultsDir = Paths.get(args[++i]);
            case "--trials"  -> trials = Integer.parseInt(args[++i]);
            case "--smoke"   -> smoke = true;
            case "--data"    -> dataDir = Paths.get(args[++i]);
            default -> {
               System.err.println("Tham số không hợp lệ: " + args[i]);
               System.exit(2);
            }
         }
      }
      if (smoke) trials = 1;

      gcs = ManagementFactory.getGarbageCollectorMXBeans();
      Files.createDirectories(resultsDir);
      Path rawFile = resultsDir.resolve("raw_fork" + fork + ".csv");

      List<DS> datasets = readTargetDatasets(dataDir, smoke);
      System.out.println("================================================================================");
      System.out.printf(Locale.ROOT, "KDiag – Đo kiểm chứng lô batch_k (fork %d)%n", fork);
      System.out.printf(Locale.ROOT, "  Chế độ: %s  |  Trials: %d  |  Số bộ N: %d  |  Đầu ra: %s%n",
                        smoke ? "SMOKE TEST" : "FULL RUN", trials, datasets.size(), rawFile);
      System.out.println("================================================================================");

      long tStart = System.nanoTime();
      jvmWarmup();

      try (BufferedWriter writer = Files.newBufferedWriter(rawFile, StandardCharsets.UTF_8))
      {
         writer.write(RAW_HEADER);
         writer.write('\n');

         int dsIndex = 0;
         for (DS ds : datasets)
         {
            dsIndex++;
            long tl0 = System.nanoTime();
            byte[] bytes = Files.readAllBytes(dataDir.resolve(ds.file()));
            if (!DataGenerator.sha256(bytes).equals(ds.sha()))
               throw new IllegalStateException("sha256 mismatch: " + ds.file());
            Integer[] base = box(decode(bytes));
            long tl1 = System.nanoTime();

            List<CK> basePairs = getPairsForN(ds.n());

            // 1. Dataset warm-up (3 rounds)
            int warmupRounds = smoke ? 1 : DATASET_WARMUP_ROUNDS;
            for (int r = 1; r <= warmupRounds; r++)
            {
               List<CK> wp = new ArrayList<>(basePairs);
               long wseed = DataGenerator.mix64((fork * 100_000_000L + ds.seed()) * 10_000L + (1000 + r));
               shufflePairs(wp, wseed);
               for (CK ck : wp) measure(base, ck.cutoff, ck.k);
            }
            long tw1 = System.nanoTime();

            // 2. Đo chính thức theo trials
            StringBuilder sb = new StringBuilder();
            long flagInDataset = 0;
            for (int t = 1; t <= trials; t++)
            {
               List<CK> tp = new ArrayList<>(basePairs);
               long tseed = DataGenerator.mix64((fork * 100_000_000L + ds.seed()) * 10_000L + t);
               shufflePairs(tp, tseed);

               for (CK ck : tp)
               {
                  long time_ns = measure(base, ck.cutoff, ck.k);
                  runOrder++;
                  if (lastGc)
                  {
                     flagInDataset++;
                     gcFlagged++;
                  }
                  sb.append(fork).append(',').append(runOrder).append(',').append(t).append(',')
                    .append(ds.n()).append(',').append(ds.seed()).append(',')
                    .append(ck.cutoff).append(',').append(ck.k).append(',')
                    .append(time_ns).append(',').append(lastGc).append('\n');
               }
            }
            writer.write(sb.toString());
            writer.flush();
            long tm1 = System.nanoTime();

            double loadS = (tl1 - tl0) / 1e9;
            double warmS = (tw1 - tl1) / 1e9;
            double measS = (tm1 - tw1) / 1e9;
            System.out.printf(Locale.ROOT, "[fork %d] %d/%d N=%5d (pairs=%2d, trials=%2d) load=%.2fs warm=%.2fs meas=%.2fs gc=%d%n",
                              fork, dsIndex, datasets.size(), ds.n(), basePairs.size(), trials, loadS, warmS, measS, flagInDataset);
         }
      }

      double totalSec = (System.nanoTime() - tStart) / 1e9;
      System.out.printf(Locale.ROOT, "================================================================================%n");
      System.out.printf(Locale.ROOT, "[fork %d] Hoàn tất trong %.2f s (%.1f phút). Tổng lần đo: %d, GC cờ: %d, Sink: %d%n",
                        fork, totalSec, totalSec / 60.0, runOrder, gcFlagged, sink);
      System.out.printf(Locale.ROOT, "================================================================================%n");
   }
}
