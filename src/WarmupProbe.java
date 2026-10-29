import java.io.*;
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Locale;

/**
 * Công cụ CHẨN ĐOÁN bước nhảy thời gian (không thuộc thí nghiệm chính, không sửa Benchmark.java).
 * Lặp lại đúng vòng warm-up JVM của Benchmark (N = 2^16, seed 777, 35 CUTOFF xáo thứ tự, gọi
 * Benchmark.measure như bản gốc) nhưng chạy nhiều vòng hơn và ghi dấu thời gian từng vòng.
 *
 * Chạy (KHÔNG -ea), từ thư mục cutoff-experiment:
 *   java -Xms2g -Xmx2g -XX:+UseSerialGC -XX:+AlwaysPreTouch -cp build WarmupProbe <rounds> <out.csv> [N1,N2,...]
 *   N mặc định 65536 (đúng warm-up của Benchmark). Nhiều N: các vòng luân phiên N1, N2, ... (vd "4096,262144"
 *   để so sánh đoạn nằm gọn trong cache với đoạn phụ thuộc bộ nhớ ở cùng một trạng thái máy).
 *
 * Mỗi dòng CSV = một vòng:
 *   round, N, epoch_ms_start, epoch_ms_end   : giờ hệ thống (đối chiếu với typeperf)
 *   uptime_ms_start, uptime_ms_end        : thời gian từ lúc JVM khởi động (đối chiếu với -Xlog ... :uptime)
 *   sort_ms                               : tổng thời gian sort của 35 lần đo (giống round_totals_ms)
 *   ns_per_NlgN                           : sort_ms chuẩn hóa = 1e6·sort_ms / (35·N·lgN)
 *   wall_ms                               : thời gian thực của cả vòng (gồm System.gc, clone)
 *   main_cpu_ms                           : CPU time của luồng main trong vòng (không gồm GC: GC chạy ở VM thread)
 *   cpu_per_sort                          : main_cpu_ms / sort_ms. Gần như không đổi nếu luồng vẫn chạy nhưng chậm
 *                                           đi (xung thấp, SMT); giảm rõ nếu luồng bị Windows tạm dừng/đẩy khỏi nhân.
 * Lưu ý: GetThreadTimes trên Windows có độ phân giải ~15.6 ms, nên cpu_per_sort mỗi vòng có sai số vài %.
 */
public final class WarmupProbe
{
   public static void main(String[] args) throws IOException
   {
      boolean ea = false;
      assert ea = true;
      if (ea) { System.err.println("run WITHOUT -ea"); System.exit(2); }
      int rounds = args.length > 0 ? Integer.parseInt(args[0]) : 300;
      Path out = Paths.get(args.length > 1 ? args[1] : "probe.csv");
      if (out.getParent() != null) Files.createDirectories(out.getParent());

      Benchmark.gcs = ManagementFactory.getGarbageCollectorMXBeans();   // như Benchmark.main
      Benchmark.fork = 1;                                                // seed thứ tự CUTOFF như fork 1
      ThreadMXBean tmx = ManagementFactory.getThreadMXBean();
      var rt = ManagementFactory.getRuntimeMXBean();
      String[] sz = (args.length > 2 ? args[2] : "65536").split(",");
      int[] ns = new int[sz.length];
      Integer[][] bases = new Integer[sz.length][];
      for (int i = 0; i < sz.length; i++)
      {
         ns[i] = Integer.parseInt(sz[i].trim());
         bases[i] = Benchmark.box(DataGenerator.generate("random", ns[i], 777L));
      }

      try (BufferedWriter w = Files.newBufferedWriter(out, StandardCharsets.UTF_8))
      {
         w.write("round,N,epoch_ms_start,epoch_ms_end,uptime_ms_start,uptime_ms_end,sort_ms,ns_per_NlgN,wall_ms,main_cpu_ms,cpu_per_sort\n");
         for (int r = 1; r <= rounds; r++)
         {
            int which = (r - 1) % ns.length;
            Integer[] base = bases[which];
            int n = ns[which];
            long e0 = System.currentTimeMillis(), u0 = rt.getUptime(), n0 = System.nanoTime();
            long c0 = tmx.getCurrentThreadCpuTime();
            long sortNs = 0;
            for (int c : Benchmark.shuffled(Benchmark.FULL_GRID, Benchmark.trialSeed(0, 5000 + r)))
               sortNs += Benchmark.measure(base, c, 1);
            long c1 = tmx.getCurrentThreadCpuTime();
            long n1 = System.nanoTime(), u1 = rt.getUptime(), e1 = System.currentTimeMillis();
            double sortMs = sortNs / 1e6, cpuMs = (c1 - c0) / 1e6;
            double perNlgN = sortNs / (35.0 * n * (Math.log(n) / Math.log(2)));
            w.write(String.format(Locale.ROOT, "%d,%d,%d,%d,%d,%d,%.2f,%.3f,%.1f,%.1f,%.3f%n",
                                  r, n, e0, e1, u0, u1, sortMs, perNlgN, (n1 - n0) / 1e6, cpuMs, cpuMs / sortMs));
            w.flush();
            if (r % 10 == 0)
               System.out.printf(Locale.ROOT, "round %d (N=%d): sort %.1f ms, cpu/sort %.2f%n", r, n, sortMs, cpuMs / sortMs);
         }
      }
      System.out.println("sink=" + Benchmark.sink);
   }
}
