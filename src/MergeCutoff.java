public class MergeCutoff
{
   private static void merge(Comparable[] a, Comparable[] aux, int lo, int mid, int hi)
   {
      assert isSorted(a, lo, mid);     // precondition: a[lo..mid] sorted
      assert isSorted(a, mid+1, hi);   // precondition: a[mid+1..hi] sorted

      for (int k = lo; k <= hi; k++)
         aux[k] = a[k];

      int i = lo, j = mid+1;
      for (int k = lo; k <= hi; k++)
      {
         if      (i > mid)              a[k] = aux[j++];
         else if (j > hi)               a[k] = aux[i++];
         else if (less(aux[j], aux[i])) a[k] = aux[j++];
         else                           a[k] = aux[i++];
      }

      assert isSorted(a, lo, hi);      // postcondition: a[lo..hi] sorted
   }

   // [SỬA] đổi tên tham số CUTOFF -> cutoff
   private static void sort(Comparable[] a, Comparable[] aux, int lo, int hi, int cutoff)
   {
      // đoạn có độ dài hi - lo + 1 <= cutoff thì sắp bằng insertion sort
      if (hi <= lo + cutoff - 1)
      {
         Insertion.sort(a, lo, hi);
         return;
      }
      int mid = lo + (hi - lo) / 2;
      sort(a, aux, lo, mid, cutoff);
      sort(a, aux, mid+1, hi, cutoff);
      merge(a, aux, lo, mid, hi);
   }

   public static void sort(Comparable[] a, int cutoff)
   {
      // [SỬA] chặn cutoff < 1: nếu không, đoạn độ dài 1 sẽ đệ quy vô hạn
      if (cutoff < 1)
         throw new IllegalArgumentException("cutoff must be >= 1");

      Comparable[] aux = new Comparable[a.length];
      sort(a, aux, 0, a.length - 1, cutoff);
   }

   private static class Insertion
   {
      public static void sort(Comparable[] a, int lo, int hi)
      {
         // [SỬA] bắt đầu từ lo + 1 như bài giảng
         for (int i = lo + 1; i <= hi; i++)
            for (int j = i; j > lo; j--)
               if (less(a[j], a[j-1]))
                  exch(a, j, j-1);
               else break;
      }
   }

   private static boolean less(Comparable v, Comparable w)
   {  return v.compareTo(w) < 0;  }

   private static void exch(Comparable[] a, int i, int j)
   {
      Comparable swap = a[i];
      a[i] = a[j];
      a[j] = swap;
   }

   private static boolean isSorted(Comparable[] a)
   {
      for (int i = 1; i < a.length; i++)
         if (less(a[i], a[i-1])) return false;
      return true;
   }

   private static boolean isSorted(Comparable[] a, int lo, int hi)
   {
      for (int i = lo + 1; i <= hi; i++)
         if (less(a[i], a[i-1])) return false;
      return true;
   }
}