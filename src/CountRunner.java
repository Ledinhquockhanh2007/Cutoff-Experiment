import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/**
 * Đếm compares / accesses / exchanges / merged_len bằng MergeCutoffCounted trên mọi bộ dữ liệu
 * x lưới CUTOFF tương ứng (random: 1..32, 40, 48, 64; phân bố khác: lưới thưa), ghi results/counts.csv.
 * Chạy trong JVM RIÊNG (không phải JVM benchmark):  java -Xmx2g -cp build CountRunner
 * Kết quả tất định: cùng data/ cho cùng counts.csv (in sha256 ở cuối để đối chiếu giữa các máy).
 * tùy chọn: --data <dir> (mặc định data), --out <file> (mặc định results/counts.csv)
 */
public final class CountRunner
{
   static final String HEADER = "distribution,N,seed,cutoff,compares,accesses,exchanges,merged_len";

   public static void main(String[] args) throws IOException
   {
      Path dataDir = Paths.get("data"), out = Paths.get("results", "counts.csv");
      for (int i = 0; i < args.length; i++)
      {
         switch (args[i])
         {
            case "--data" -> dataDir = Paths.get(args[++i]);
            case "--out"  -> out = Paths.get(args[++i]);
            default -> { System.err.println("unknown argument: " + args[i]); System.exit(2); }
         }
      }
      List<Benchmark.DS> all = Benchmark.readManifest(dataDir);   // cùng manifest, cùng lưới với Benchmark
      if (out.getParent() != null) Files.createDirectories(out.getParent());
      long t0 = System.nanoTime();
      int rows = 0;
      try (BufferedWriter w = Files.newBufferedWriter(out, StandardCharsets.UTF_8))
      {
         w.write(HEADER); w.write('\n');
         int idx = 0;
         for (Benchmark.DS ds : all)
         {
            idx++;
            byte[] bytes = Files.readAllBytes(dataDir.resolve(ds.file()));
            if (!DataGenerator.sha256(bytes).equals(ds.sha())) fail("sha256 mismatch: " + ds.file());
            Integer[] base = Benchmark.box(Benchmark.decode(bytes));
            StringBuilder sb = new StringBuilder();
            for (int c : Benchmark.gridFor(ds.dist()))
            {
               Integer[] a = base.clone();
               MergeCutoffCounted.reset();
               MergeCutoffCounted.sort(a, c);
               long C = MergeCutoffCounted.getCompares(), A = MergeCutoffCounted.getAccesses();
               long E = MergeCutoffCounted.getExchanges(), S = MergeCutoffCounted.getMergedLen();
               if (!Benchmark.isSorted(a)) fail("not sorted: " + ds.file() + " cutoff=" + c);
               if (A != 4 * S + 2 * C + 4 * E) fail("A != 4S+2C+4E: " + ds.file() + " cutoff=" + c);
               sb.append(ds.dist()).append(',').append(ds.n()).append(',').append(ds.seed()).append(',')
                 .append(c).append(',').append(C).append(',').append(A).append(',').append(E).append(',')
                 .append(S).append('\n');
               rows++;
            }
            w.write(sb.toString());
            w.flush();
            System.out.printf(Locale.ROOT, "%3d/%d %-13s N=%7d  (%.0f s)%n",
                              idx, all.size(), ds.dist(), ds.n(), (System.nanoTime() - t0) / 1e9);
         }
      }
      System.out.printf(Locale.ROOT, "wrote %d rows to %s in %.0f s%n", rows, out, (System.nanoTime() - t0) / 1e9);
      System.out.println("sha256(counts.csv) = " + DataGenerator.sha256(Files.readAllBytes(out)));
   }

   static void fail(String msg)
   {
      System.err.println("FATAL: " + msg);
      System.exit(3);
   }
}
