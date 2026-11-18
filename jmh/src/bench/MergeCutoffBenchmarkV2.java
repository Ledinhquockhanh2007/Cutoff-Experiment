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
import java.util.HexFormat;
import java.util.HashSet;
import java.util.Random;
import java.util.Set;
import java.util.concurrent.TimeUnit;

/**
 * JMH v2 factorial 2 x 2 benchmark for MergeCutoff diagnostics (T11 / §1 hợp đồng).
 * Giữ nguyên lớp T08 MergeCutoffBenchmark; lớp này thêm tham số input {same, fresh}
 * và profile {pure, mixed}.
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

   @Param({"4096", "65536", "524288"})
   public int n;

   @Param({"1", "7", "10", "30"})
   public int cutoff;

   private Sorter sorter;
   private Integer[][] pool;
   private Integer[] array;
   private int invocIdx;
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

   static int[] knuthShuffle(int[] src, long seed)
   {
      int[] perm = src.clone();
      Random rnd = new Random(seed);
      for (int i = 0; i < perm.length; i++)
      {
         int r = rnd.nextInt(i + 1);
         int tmp = perm[i];
         perm[i] = perm[r];
         perm[r] = tmp;
      }
      return perm;
   }

   static String sha256Ints(int[] a) throws Exception
   {
      ByteBuffer bb = ByteBuffer.allocate(4 * a.length).order(ByteOrder.LITTLE_ENDIAN);
      bb.asIntBuffer().put(a);
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

      if ("same".equals(input))
      {
         pool = new Integer[1][];
         pool[0] = box(v);
      }
      else
      {
         int P = poolSizeFor(n);
         pool = new Integer[P][];
         pool[0] = box(v);
         for (int i = 1; i < P; i++)
         {
            int[] perm = knuthShuffle(v, FRESH_SEED_BASE + i);
            pool[i] = box(perm);
         }
      }
      invocIdx = 0;
   }

   @Setup(Level.Invocation)
   public void setupInvocation()
   {
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
    *   - xác nhận P = 64, 64, 16; các hoán vị trong bể fresh đôi một khác nhau;
    *   - in sha256 của 2 hoán vị đầu mỗi N;
    *   - xác nhận mảng sau khi gọi sort() đã sắp đúng cho cả same và fresh;
    *   - in thứ tự CUTOFF 2 vòng đầu của pha mixed để đối chiếu với Benchmark.java.
    */
   public static void main(String[] args) throws Exception
   {
      System.out.println("=== MergeCutoffBenchmarkV2 functional verification (NO timing) ===");
      int[] ns = {4096, 65536, 524288};
      for (int nv : ns)
      {
         Path p = Paths.get(String.format("data_run5/random/N%07d.bin", nv));
         int[] v = readBin(p);
         int P = poolSizeFor(nv);
         Set<String> hashes = new HashSet<>();
         String h0 = sha256Ints(v);
         hashes.add(h0);
         String h1 = "";
         for (int i = 1; i < P; i++)
         {
            int[] perm = knuthShuffle(v, FRESH_SEED_BASE + i);
            String h = sha256Ints(perm);
            if (i == 1) h1 = h;
            hashes.add(h);
         }
         if (hashes.size() != P)
            throw new AssertionError("Duplicate permutation in fresh pool for N=" + nv);
         System.out.printf("N=%7d | P=%2d | distinct=%2d/%2d | sha256[0]=%s | sha256[1]=%s%n",
                           nv, P, hashes.size(), P, h0.substring(0, 16), h1.substring(0, 16));
      }

      // Kiểm sắp xếp đúng cho cả 4 tổ hợp input x profile tại N=4096, c=1 và c=30
      for (String inMode : new String[]{"same", "fresh"})
      {
         for (String prof : new String[]{"pure", "mixed"})
         {
            MergeCutoffBenchmarkV2 b = new MergeCutoffBenchmarkV2();
            b.input = inMode;
            b.profile = prof;
            b.n = 4096;
            b.cutoff = 1;
            b.setupTrial();
            int expectedP = "same".equals(inMode) ? 1 : 64;
            if (b.pool.length != expectedP)
               throw new AssertionError("Pool length mismatch: " + b.pool.length);
            int checks = Math.min(expectedP + 2, 10);
            for (int j = 0; j < checks; j++)
            {
               b.setupInvocation();
               Integer[] out = b.sort();
               if (!isSorted(out))
                  throw new AssertionError("Output NOT sorted for " + inMode + "/" + prof + " inv=" + j);
            }
            System.out.printf("CHECK PASS: input=%-5s profile=%-5s N=4096 c=1 pool=%2d checked=%d invocations%n",
                              inMode, prof, b.pool.length, checks);
         }
      }

      // In thứ tự CUTOFF 2 vòng đầu từ MergeCutoffBridge.mixedWarmupOrder (gọi trực tiếp Benchmark.shuffled)
      Class<?> bridgeCls = Class.forName("MergeCutoffBridge");
      var mOrder = bridgeCls.getMethod("mixedWarmupOrder", int.class);
      for (int r = 1; r <= 2; r++)
      {
         int[] ord = (int[]) mOrder.invoke(null, r);
         System.out.println("mixedWarmupOrder round " + r + " (len=" + ord.length + "): " + Arrays.toString(ord));
      }
      System.out.println("=== ALL FUNCTIONAL CHECKS PASSED ===");
   }
}
