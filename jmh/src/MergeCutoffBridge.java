public class MergeCutoffBridge implements bench.Sorter
{
   @Override
   public void sort(Comparable[] a, int cutoff)
   {
      MergeCutoff.sort(a, cutoff);
   }

   /** Thứ tự CUTOFF vòng r (1-based) đúng như Benchmark.jvmWarmup (fork = 1, seed = 0, t = 5000 + r). */
   public static int[] mixedWarmupOrder(int round)
   {
      long seed = DataGenerator.mix64((1L * 100_000_000L + 0L) * 10_000L + (5000L + round));
      return Benchmark.shuffled(Benchmark.FULL_GRID, seed);
   }

   /**
    * Tái hiện pha JVM warm-up của Benchmark.java (N = 65536, seed 777, FULL_GRID 35 cutoff,
    * thứ tự xáo giống harness, cố định `rounds` vòng = 11) mà không ghi tệp.
    */
   @Override
   public long mixedWarmup(int rounds)
   {
      int[] raw = DataGenerator.generate("random", Benchmark.JVM_WARMUP_N, Benchmark.JVM_WARMUP_SEED);
      Integer[] base = Benchmark.box(raw);
      long sink = 0;
      for (int r = 1; r <= rounds; r++)
      {
         for (int c : mixedWarmupOrder(r))
         {
            Integer[] copy = base.clone();
            MergeCutoff.sort(copy, c);
            if (copy.length > 0)
               sink += copy[0] + 31L * copy[copy.length / 2] + 961L * copy[copy.length - 1];
         }
      }
      System.gc();
      return sink;
   }
}
