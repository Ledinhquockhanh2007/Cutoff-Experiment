package bench;

import org.openjdk.jmh.annotations.*;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.IntBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.IdentityHashMap;
import java.util.Random;
import java.util.Set;
import java.util.concurrent.TimeUnit;

/**
 * JMH v2 factorial benchmark for MergeCutoff diagnostics (T11 / §1 + Phụ lục A1-A3).
 * Giữ nguyên lớp T08 MergeCutoffBenchmark; lớp này có tham số:
 *   - input   {same, fresh} (A1: bể fresh dùng CHUNG đúng N đối tượng Integer của hoán vị 0)
 *   - profile {pure, mixed}
 *   - reset   {none, gc}    (A2: gc gọi System.gc() đầu @Setup(Level.Invocation) trước clone)
 *   - n       {4096, 65536, 524288}
 *   - cutoff  {1, 7, 10, 30}
 */
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 10, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(3)
@State(Scope.Thread)
public class MergeCutoffBenchmarkV2
{
   public static final int MIXED_WARMUP_ROUNDS = 11;
   public static final long FRESH_SEED_BASE = 20261118L * 1000L;

   @Param({"same", "fresh"})
   public String input;

   @Param({"pure", "mixed"})
   public String profile;

   @Param({"none", "gc"})
   public String reset;

   @Param({"4096", "65536", "524288"})
   public int n;

   @Param({"1", "7", "10", "30"})
   public int cutoff;

   private Sorter sorter;
   private Integer[][] pool;
   private Integer[] array;
   private int invocIdx;
   private boolean doGcReset;
   public long mixedSink;

   static int[] readBin(Path p) throws IOException
   {
      byte[] b = Files.readAllBytes(p);
      IntBuffer ib = ByteBuffer.wrap(b).order(ByteOrder.LITTLE_ENDIAN).asIntBuffer();
      int[] a = new int[ib.remaining()];
      ib.get(a);
      return a;
   }

   static Integer[] box(int[] v)
   {
      Integer[] a = new Integer[v.length];
      for (int i = 0; i < v.length; i++) a[i] = Integer.valueOf(v[i]);
      return a;
   }

   static int poolSizeFor(int n)
   {
      return Math.min(64, (1 << 23) / n);
   }

   /** A1: xáo mảng tham chiếu Integer[] tới cùng bộ đối tượng của hoán vị 0 (Knuth shuffle). */
   static Integer[] knuthShuffleRefs(Integer[] base, long seed)
   {
      Integer[] perm = base.clone();
      Random rnd = new Random(seed);
      for (int i = 0; i < perm.length; i++)
      {
         int r = rnd.nextInt(i + 1);
         Integer tmp = perm[i];
         perm[i] = perm[r];
         perm[r] = tmp;
      }
      return perm;
   }

   static String sha256IntegerValues(Integer[] a) throws Exception
   {
      ByteBuffer bb = ByteBuffer.allocate(4 * a.length).order(ByteOrder.LITTLE_ENDIAN);
      IntBuffer ib = bb.asIntBuffer();
      for (int i = 0; i < a.length; i++) ib.put(a[i].intValue());
      byte[] dig = MessageDigest.getInstance("SHA-256").digest(bb.array());
      return HexFormat.of().formatHex(dig);
   }

   static boolean isSorted(Integer[] a)
   {
      for (int i = 1; i < a.length; i++)
         if (a[i].intValue() < a[i - 1].intValue()) return false;
      return true;
   }

   @Setup(Level.Trial)
   public void setupTrial() throws Exception
   {
      if (!"same".equals(input) && !"fresh".equals(input))
         throw new IllegalArgumentException("Unknown input param: " + input);
      if (!"pure".equals(profile) && !"mixed".equals(profile))
         throw new IllegalArgumentException("Unknown profile param: " + profile);
      if (!"none".equals(reset) && !"gc".equals(reset))
         throw new IllegalArgumentException("Unknown reset param: " + reset);

      doGcReset = "gc".equals(reset);
      sorter = (Sorter) Class.forName("MergeCutoffBridge").getDeclaredConstructor().newInstance();

      // Pha mixed chạy TRƯỚC warm-up của JMH để hồ sơ JIT giống Benchmark.java
      if ("mixed".equals(profile))
      {
         mixedSink += sorter.mixedWarmup(MIXED_WARMUP_ROUNDS);
      }

      Path p = Paths.get(String.format("data_run5/random/N%07d.bin", n));
      int[] v = readBin(p);
      if (v.length != n)
         throw new IllegalStateException("Expected length " + n + ", got " + v.length);

      // A1: tạo bộ đối tượng Integer MỘT lần từ hoán vị 0 (đúng T08)
      Integer[] base = box(v);

      if ("same".equals(input))
      {
         pool = new Integer[1][];
         pool[0] = base;
      }
      else
      {
         int P = poolSizeFor(n);
         pool = new Integer[P][];
         pool[0] = base;
         for (int i = 1; i < P; i++)
         {
            pool[i] = knuthShuffleRefs(base, FRESH_SEED_BASE + i);
         }
      }
      invocIdx = 0;
   }

   @Setup(Level.Invocation)
   public void setupInvocation()
   {
      // A2: khi reset=gc, gọi System.gc() TRƯỚC clone (đúng thứ tự Benchmark.measure)
      if (doGcReset) System.gc();
      array = pool[invocIdx].clone();
      invocIdx++;
      if (invocIdx == pool.length) invocIdx = 0;
   }

   @Benchmark
   public Integer[] sort()
   {
      sorter.sort(array, cutoff);
      return array;
   }

   /**
    * Kiểm tra tính đúng (không đo thời gian, không in thời gian hay r):
    *   - A1: mọi pool[i][j] là đối tượng của pool[0] (so bằng == qua IdentityHashMap),
    *         tổng số đối tượng Integer phân biệt trong bể = N;
    *   - sha256 dãy giá trị của 2 hoán vị đầu mỗi N trùng khớp với bản R11;
    *   - xác nhận mảng sau khi gọi sort() đã sắp đúng cho same/fresh x pure/mixed x none/gc.
    */
   public static void main(String[] args) throws Exception
   {
      System.out.println("=== MergeCutoffBenchmarkV2 functional verification A1+A2 (NO timing) ===");
      int[] ns = {4096, 65536, 524288};
      String[][] r11Refs = {
         {"f68779fbba2b6e00", "9e4bd1196ca1b4de"},
         {"8ea72d580401b26d", "01969e735afce13d"},
         {"579f240dc9c1b610", "16504670addc9645"},
      };

      for (int idx = 0; idx < ns.length; idx++)
      {
         int nv = ns[idx];
         Path p = Paths.get(String.format("data_run5/random/N%07d.bin", nv));
         int[] v = readBin(p);
         int P = poolSizeFor(nv);

         Integer[] base = box(v);
         Integer[][] testPool = new Integer[P][];
         testPool[0] = base;
         for (int i = 1; i < P; i++) testPool[i] = knuthShuffleRefs(base, FRESH_SEED_BASE + i);

         // A1: kiểm tra danh tính đối tượng bằng IdentityHashMap (so sánh ==)
         IdentityHashMap<Integer, Boolean> baseIds = new IdentityHashMap<>(nv * 2);
         for (Integer obj : testPool[0]) baseIds.put(obj, Boolean.TRUE);
         if (baseIds.size() != nv)
            throw new AssertionError("Base pool does not have N distinct Integer objects: " + baseIds.size());

         IdentityHashMap<Integer, Boolean> allPoolIds = new IdentityHashMap<>(nv * 2);
         Set<String> valueHashes = new HashSet<>();
         String h0 = "", h1 = "";
         for (int i = 0; i < P; i++)
         {
            for (int j = 0; j < nv; j++)
            {
               Integer obj = testPool[i][j];
               if (!baseIds.containsKey(obj))
                  throw new AssertionError("pool[" + i + "][" + j + "] is NOT identical (==) to any object in pool[0]");
               allPoolIds.put(obj, Boolean.TRUE);
            }
            String h = sha256IntegerValues(testPool[i]);
            if (i == 0) h0 = h.substring(0, 16);
            if (i == 1) h1 = h.substring(0, 16);
            valueHashes.add(h);
         }

         if (allPoolIds.size() != nv)
            throw new AssertionError("Expected " + nv + " distinct objects in pool, got " + allPoolIds.size());
         if (valueHashes.size() != P)
            throw new AssertionError("Duplicate value permutation in fresh pool for N=" + nv);
         if (!h0.equals(r11Refs[idx][0]) || !h1.equals(r11Refs[idx][1]))
            throw new AssertionError("SHA-256 mismatch vs R11 for N=" + nv + ": got " + h0 + "/" + h1);

         System.out.printf("A1 PASS N=%7d | P=%2d | distinct_objs=%7d/%7d | distinct_perms=%2d/%2d | sha256[0]=%s (R11=%s) | sha256[1]=%s (R11=%s)%n",
                           nv, P, allPoolIds.size(), nv, valueHashes.size(), P, h0, r11Refs[idx][0], h1, r11Refs[idx][1]);
      }

      // Kiểm sắp xếp đúng cho same/fresh x pure/mixed x none/gc tại N=4096, c=1
      String[][] cases = {
         {"same",  "pure",  "none"},
         {"fresh", "pure",  "none"},
         {"same",  "mixed", "none"},
         {"fresh", "mixed", "none"},
         {"same",  "mixed", "gc"},
         {"fresh", "mixed", "gc"},
      };
      for (String[] cfg : cases)
      {
         MergeCutoffBenchmarkV2 b = new MergeCutoffBenchmarkV2();
         b.input = cfg[0];
         b.profile = cfg[1];
         b.reset = cfg[2];
         b.n = 4096;
         b.cutoff = 1;
         b.setupTrial();
         int checks = "same".equals(cfg[0]) ? 3 : 6;
         for (int j = 0; j < checks; j++)
         {
            b.setupInvocation();
            Integer[] out = b.sort();
            if (!isSorted(out))
               throw new AssertionError("Output NOT sorted for " + Arrays.toString(cfg) + " inv=" + j);
         }
         System.out.printf("CHECK PASS: input=%-5s profile=%-5s reset=%-4s N=4096 c=1 pool=%2d checked=%d%n",
                           cfg[0], cfg[1], cfg[2], b.pool.length, checks);
      }
      System.out.println("=== ALL A1+A2 FUNCTIONAL CHECKS PASSED ===");
   }
}
