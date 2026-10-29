/**
 * Bản ĐẾM của MergeCutoff: chỉ dùng để đếm, KHÔNG dùng để đo thời gian.
 * Sao từ MergeCutoff.java: xóa các assert, chèn bộ đếm (đánh dấu [ĐẾM]), giữ nguyên logic.
 *
 * Quy ước đếm (Sedgewick):
 *   compares  = số lần thuật toán so sánh (lessCounted); less() gọi từ isSorted KHÔNG được đếm
 *   accesses  = mọi lần đọc/ghi a[] hoặc aux[]:
 *               copy sang aux = 2 / phần tử, a[k] = aux[..] = 2, mỗi phép so sánh = 2 lần đọc, exch = 4
 *   exchanges = số lần exch (E)
 *   mergedLen = S = tổng độ dài các đoạn được merge
 * Các bộ đếm cộng dồn qua các lần sort: gọi reset() trước mỗi lần đếm.
 */
public class MergeCutoffCounted
{
   private static long compares, accesses, exchanges, mergedLen;   // [ĐẾM]

   public static void reset()        { compares = accesses = exchanges = mergedLen = 0; }   // [ĐẾM]
   public static long getCompares()  { return compares;  }                                // [ĐẾM]
   public static long getAccesses()  { return accesses;  }                                // [ĐẾM]
   public static long getExchanges() { return exchanges; }                                // [ĐẾM]
   public static long getMergedLen() { return mergedLen; }                                // [ĐẾM]

   private static void merge(Comparable[] a, Comparable[] aux, int lo, int mid, int hi)
   {
      mergedLen += hi - lo + 1;                       // [ĐẾM] S

      for (int k = lo; k <= hi; k++)
      {
         aux[k] = a[k];
         accesses += 2;                               // [ĐẾM] 1 đọc a[k] + 1 ghi aux[k]
      }

      int i = lo, j = mid+1;
      for (int k = lo; k <= hi; k++)
      {
         accesses += 2;                               // [ĐẾM] a[k] = aux[..]: 1 đọc + 1 ghi
         if      (i > mid)                     a[k] = aux[j++];
         else if (j > hi)                      a[k] = aux[i++];
         else if (lessCounted(aux[j], aux[i])) a[k] = aux[j++];
         else                                  a[k] = aux[i++];
      }
   }

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
      if (cutoff < 1)
         throw new IllegalArgumentException("cutoff must be >= 1");

      Comparable[] aux = new Comparable[a.length];
      sort(a, aux, 0, a.length - 1, cutoff);
   }

   private static class Insertion
   {
      public static void sort(Comparable[] a, int lo, int hi)
      {
         for (int i = lo + 1; i <= hi; i++)
            for (int j = i; j > lo; j--)
               if (lessCounted(a[j], a[j-1]))
                  exch(a, j, j-1);
               else break;
      }
   }

   // [ĐẾM] phép so sánh của thuật toán: 1 compare + 2 lần đọc mảng để lấy toán hạng
   private static boolean lessCounted(Comparable v, Comparable w)
   {
      compares++;
      accesses += 2;
      return v.compareTo(w) < 0;
   }

   // giữ nguyên, chỉ dùng cho isSorted, không đếm
   private static boolean less(Comparable v, Comparable w)
   {  return v.compareTo(w) < 0;  }

   private static void exch(Comparable[] a, int i, int j)
   {
      exchanges++;                                    // [ĐẾM]
      accesses += 4;                                  // [ĐẾM] 2 đọc + 2 ghi
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
