package bench;

public interface Sorter
{
   void sort(Comparable[] a, int cutoff);

   default long mixedWarmup(int rounds)
   {
      throw new UnsupportedOperationException("mixedWarmup not implemented");
   }
}
