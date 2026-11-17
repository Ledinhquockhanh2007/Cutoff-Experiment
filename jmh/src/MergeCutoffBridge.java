public class MergeCutoffBridge implements bench.Sorter
{
   @Override
   public void sort(Comparable[] a, int cutoff)
   {
      MergeCutoff.sort(a, cutoff);
   }
}
