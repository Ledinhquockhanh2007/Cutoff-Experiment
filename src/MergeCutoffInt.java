public class MergeCutoffInt
{
    private static void merge(int[] a, int[] aux, int lo, int mid, int hi)
    {
        assert isSorted(a, lo, mid);
        assert isSorted(a, mid+1, hi);

        for (int k = lo; k <= hi; k++)
            aux[k] = a[k];

        int i = lo, j = mid+1;
        for (int k = lo; k <= hi; k++)
        {
            if      (i > mid)          a[k] = aux[j++];
            else if (j > hi)           a[k] = aux[i++];
            else if (aux[j] < aux[i])  a[k] = aux[j++];
            else                       a[k] = aux[i++];
        }

        assert isSorted(a, lo, hi);
    }

    private static void sort(int[] a, int[] aux, int lo, int hi, int cutoff)
    {
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

    public static void sort(int[] a, int cutoff)
    {
        if (cutoff < 1)
            throw new IllegalArgumentException("cutoff must be >= 1");

        int[] aux = new int[a.length];
        sort(a, aux, 0, a.length - 1, cutoff);
    }

    private static class Insertion
    {
        public static void sort(int[] a, int lo, int hi)
        {
            for (int i = lo + 1; i <= hi; i++)
                for (int j = i; j > lo; j--)
                    if (a[j] < a[j-1])
                        exch(a, j, j-1);
                    else break;
        }
    }

    private static void exch(int[] a, int i, int j)
    {
        int swap = a[i];
        a[i] = a[j];
        a[j] = swap;
    }

    private static boolean isSorted(int[] a)
    {
        for (int i = 1; i < a.length; i++)
            if (a[i] < a[i-1]) return false;
        return true;
    }

    private static boolean isSorted(int[] a, int lo, int hi)
    {
        for (int i = lo + 1; i <= hi; i++)
            if (a[i] < a[i-1]) return false;
        return true;
    }
}