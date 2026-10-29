import java.util.*;

/**
 * Kiểm tra tính đúng của MergeCutoff, MergeCutoffCounted và DataGenerator.
 * Chạy trong JVM RIÊNG với -ea:  java -ea -cp build CorrectnessTest
 * JVM benchmark không bao giờ chạy file này (tránh làm bẩn type profile của compareTo).
 * Thoát với mã 0 nếu mọi nhóm PASS, 1 nếu có FAIL.
 */
public class CorrectnessTest
{
   // ------------------------------------------------------------------ bookkeeping

   private static final Map<String, long[]> TALLY = new LinkedHashMap<>();       // nhóm -> {pass, fail}
   private static final Map<String, List<String>> FAILS = new LinkedHashMap<>();  // vài lỗi đầu tiên
   private static final int MAX_MSGS = 5;

   private static void check(String group, boolean ok, String fmt, Object... args)
   {
      long[] t = TALLY.computeIfAbsent(group, g -> new long[2]);
      if (ok) { t[0]++; return; }
      t[1]++;
      List<String> l = FAILS.computeIfAbsent(group, g -> new ArrayList<>());
      if (l.size() < MAX_MSGS) l.add(String.format(fmt, args));
   }

   private static final String G_EA     = "00. JVM runs with -ea";
   private static final String G_GEN    = "01. DataGenerator: values, encoding, determinism, plan";
   private static final String G_SORT   = "02. isSorted (N=0..300 x cutoff=1..70 x 5 distributions)";
   private static final String G_PERM   = "03. output is a permutation of input (vs Arrays.sort)";
   private static final String G_SAME   = "04. MergeCutoff == MergeCutoffCounted (same objects, same order)";
   private static final String G_STAB   = "05. stability (Item(key, idx))";
   private static final String G_CUT    = "06. cutoff < 1 -> IllegalArgumentException";
   private static final String G_CBND   = "07. 1/2 N lgN <= C <= N lgN (cutoff=1, N=2^k)";
   private static final String G_SPOW   = "08. S = N(lgN - m) (N=2^k, cutoff=2^m, m<k)";
   private static final String G_SSIM   = "09. S = simulated recursion tree (independent)";
   private static final String G_AID    = "10. A = 4S + 2C + 4E";
   private static final String G_EINV   = "11. E = inversions of original array on leaves (independent)";
   private static final String G_INS    = "12. insertion alone: sorted / reversed, k=1..50";
   private static final String G_THROW  = "13. no unexpected exception";
   private static final String G_TREE   = "14. MergeCutoff (timed version) has same tree: compares match";

   // ------------------------------------------------------------------ helpers

   static final int OFFSET = DataGenerator.OFFSET;
   static final List<String> DISTS = DataGenerator.DISTRIBUTIONS;

   static final class Item implements Comparable<Item>
   {
      final int key, idx;
      Item(int key, int idx) { this.key = key; this.idx = idx; }
      @Override public int compareTo(Item o) { return Integer.compare(key, o.key); }
   }

   /** Khóa có bộ đếm compareTo: đếm số phép so sánh của MergeCutoff (bản đo) mà không sửa code của nó. */
   static final class Key implements Comparable<Key>
   {
      static long count = 0;
      final int v;
      Key(int v) { this.v = v; }
      @Override public int compareTo(Key o) { count++; return Integer.compare(v, o.v); }
   }

   static Key[] keys(int[] v)
   {
      Key[] a = new Key[v.length];
      for (int i = 0; i < v.length; i++) a[i] = new Key(v[i]);
      return a;
   }

   static boolean assertionsOn()
   {
      boolean ea = false;
      assert ea = true;
      return ea;
   }

   static Integer[] box(int[] v)
   {
      Integer[] a = new Integer[v.length];
      for (int i = 0; i < v.length; i++) a[i] = Integer.valueOf(v[i]);
      return a;
   }

   static boolean isSorted(Comparable[] a)
   {
      for (int i = 1; i < a.length; i++)
         if (a[i].compareTo(a[i - 1]) < 0) return false;
      return true;
   }

   static boolean sameValues(Integer[] a, int[] expected)
   {
      if (a.length != expected.length) return false;
      for (int i = 0; i < a.length; i++) if (a[i].intValue() != expected[i]) return false;
      return true;
   }

   static boolean sameObjects(Object[] a, Object[] b)
   {
      if (a.length != b.length) return false;
      for (int i = 0; i < a.length; i++) if (a[i] != b[i]) return false;
      return true;
   }

   /** Mô phỏng cây đệ quy theo ĐỊNH NGHĨA "độ dài <= cutoff là lá"; trả về S, ghi các lá vào leaves. */
   static long simulate(int lo, int hi, int cutoff, List<int[]> leaves)
   {
      if (hi - lo + 1 <= cutoff) { leaves.add(new int[]{lo, hi}); return 0; }
      int mid = lo + (hi - lo) / 2;
      return simulate(lo, mid, cutoff, leaves) + simulate(mid + 1, hi, cutoff, leaves) + (hi - lo + 1);
   }

   static long countInternal(int lo, int hi, int cutoff)
   {
      if (hi - lo + 1 <= cutoff) return 0;
      int mid = lo + (hi - lo) / 2;
      return 1 + countInternal(lo, mid, cutoff) + countInternal(mid + 1, hi, cutoff);
   }

   /** Số nghịch thế ngặt (p < q, v[q] < v[p]) trong v[lo..hi], brute force. */
   static long inversions(int[] v, int lo, int hi)
   {
      long inv = 0;
      for (int p = lo; p <= hi; p++)
         for (int q = p + 1; q <= hi; q++)
            if (v[q] < v[p]) inv++;
      return inv;
   }

   static long[] counted(Comparable[] a, int cutoff)
   {
      MergeCutoffCounted.reset();
      MergeCutoffCounted.sort(a, cutoff);
      return new long[]{ MergeCutoffCounted.getCompares(), MergeCutoffCounted.getAccesses(),
                         MergeCutoffCounted.getExchanges(), MergeCutoffCounted.getMergedLen() };
   }

   // ------------------------------------------------------------------ groups

   static void testAssertionsEnabled()
   {
      check(G_EA, assertionsOn(), "assertions are disabled: run with java -ea");
   }

   static void testGenerator()
   {
      int[] ns = {0, 1, 2, 7, 99, 100, 101, 1000, 4096, 65536};
      for (String d : DISTS)
         for (int n : ns)
         {
            long seed = DataGenerator.seedFor(d, n);
            int[] v = DataGenerator.generate(d, n, seed);
            check(G_GEN, v.length == n, "%s N=%d: length %d", d, n, v.length);
            check(G_GEN, Arrays.equals(v, DataGenerator.generate(d, n, seed)), "%s N=%d: not deterministic", d, n);
            boolean geOffset = true;
            for (int x : v) if (x < OFFSET) geOffset = false;
            check(G_GEN, geOffset, "%s N=%d: value < OFFSET", d, n);

            int[] s = v.clone(); Arrays.sort(s);
            boolean isPermOfRange = true;
            for (int i = 0; i < n; i++) if (s[i] != OFFSET + i) isPermOfRange = false;
            switch (d)
            {
               case "random" -> check(G_GEN, isPermOfRange, "random N=%d: not a permutation of OFFSET..OFFSET+N-1", n);
               case "sorted" -> {
                  boolean ok = true;
                  for (int i = 0; i < n; i++) if (v[i] != OFFSET + i) ok = false;
                  check(G_GEN, ok, "sorted N=%d: v[i] != OFFSET+i", n);
               }
               case "reversed" -> {
                  boolean ok = true;
                  for (int i = 0; i < n; i++) if (v[i] != OFFSET + n - 1 - i) ok = false;
                  check(G_GEN, ok, "reversed N=%d: v[i] != OFFSET+N-1-i", n);
               }
               case "nearly_sorted" -> {
                  int moved = 0;
                  for (int i = 0; i < n; i++) if (v[i] != OFFSET + i) moved++;
                  check(G_GEN, isPermOfRange, "nearly_sorted N=%d: not a permutation", n);
                  check(G_GEN, moved <= 2 * (n / 100), "nearly_sorted N=%d: %d positions moved > 2*floor(N/100)", n, moved);
               }
               case "few_distinct" -> {
                  boolean ok = true;
                  for (int x : v) if ((x - OFFSET) % 1000 != 0 || (x - OFFSET) / 1000 > 9) ok = false;
                  check(G_GEN, ok, "few_distinct N=%d: value outside {OFFSET+1000k, k=0..9}", n);
               }
               default -> check(G_GEN, false, "unknown distribution %s", d);
            }
            // round-trip qua định dạng file (int32 little-endian)
            byte[] b = DataGenerator.toBytes(v);
            boolean le = n == 0 || (b[0] == (byte) v[0] && b[3] == (byte) (v[0] >>> 24));
            check(G_GEN, b.length == 4 * n && le, "%s N=%d: byte encoding", d, n);
         }
      // không dùng Integer cache
      check(G_GEN, Integer.valueOf(OFFSET) != Integer.valueOf(OFFSET),
            "Integer.valueOf(OFFSET) is cached (AutoBoxCacheMax set?)");
      // kế hoạch: 72 random + 96 phân bố khác, seed duy nhất, N trong [S, 2S)
      List<DataGenerator.Spec> plan = DataGenerator.plan();
      check(G_GEN, plan.size() == 3 * 24 + 4 * 24, "plan has %d specs", plan.size());
      Set<Long> seeds = new HashSet<>();
      for (DataGenerator.Spec sp : plan) seeds.add(sp.seed());
      check(G_GEN, seeds.size() == plan.size(), "duplicate seeds in plan");
      for (int s : new int[]{1 << 12, 1 << 16, 1 << 19})
      {
         int[] scale = DataGenerator.scaleNs(s);
         boolean ok = scale.length == 24 && scale[0] == s;
         for (int j = 0; j < scale.length; j++)
         {
            if (scale[j] < s || scale[j] >= 2 * s) ok = false;
            if (j > 0 && scale[j] <= scale[j - 1]) ok = false;
         }
         check(G_GEN, ok, "scaleNs(%d) not strictly increasing in [S, 2S)", s);
      }
   }

   /** Nhóm 2, 3, 4, 9, 10, 11: N = 0..300 x cutoff = 1..70 x 5 phân bố. */
   static void testGrid()
   {
      for (String d : DISTS)
         for (int n = 0; n <= 300; n++)
            for (int c = 1; c <= 70; c++)
            {
               long seed = DataGenerator.seedFor(d, n) * 1000 + c;    // dữ liệu khác nhau cho mỗi (N, cutoff)
               int[] v = DataGenerator.generate(d, n, seed);
               int[] expected = v.clone();
               Arrays.sort(expected);
               Integer[] base = box(v);
               Integer[] a1 = base.clone(), a2 = base.clone();
               long[] cnt;
               try
               {
                  MergeCutoff.sort(a1, c);
                  cnt = counted(a2, c);
               }
               catch (Throwable t)
               {
                  check(G_THROW, false, "%s N=%d cutoff=%d: %s", d, n, c, t);
                  continue;
               }
               check(G_THROW, true, "");
               long C = cnt[0], A = cnt[1], E = cnt[2], S = cnt[3];

               check(G_SORT, isSorted(a1) && isSorted(a2), "%s N=%d cutoff=%d", d, n, c);
               check(G_PERM, sameValues(a1, expected) && sameValues(a2, expected), "%s N=%d cutoff=%d", d, n, c);
               check(G_SAME, sameObjects(a1, a2), "%s N=%d cutoff=%d", d, n, c);
               check(G_AID, A == 4 * S + 2 * C + 4 * E,
                     "%s N=%d cutoff=%d: A=%d, 4S+2C+4E=%d", d, n, c, A, 4 * S + 2 * C + 4 * E);

               List<int[]> leaves = new ArrayList<>();
               long sSim = simulate(0, n - 1, c, leaves);
               check(G_SSIM, S == sSim, "%s N=%d cutoff=%d: S=%d, simulated=%d", d, n, c, S, sSim);

               long inv = 0;
               for (int[] lf : leaves) inv += inversions(v, lf[0], lf[1]);
               check(G_EINV, E == inv, "%s N=%d cutoff=%d: E=%d, inversions on leaves=%d", d, n, c, E, inv);

               // Nhóm 14: cây đệ quy của bản ĐO. Với -ea, mỗi merge của MergeCutoff còn gọi 3 lần isSorted
               // (đều đúng) tốn (mid-lo) + (hi-mid-1) + (hi-lo) = 2*len - 3 phép so sánh, tổng = 2S - 3M,
               // M = số lần merge = số nút trong. Phụ thuộc vào 3 assert hiện có trong MergeCutoff.merge.
               long merges = countInternal(0, n - 1, c);
               long expectTimed = C + (assertionsOn() ? 2 * sSim - 3 * merges : 0);
               Key[] k = keys(v);
               Key.count = 0;
               try { MergeCutoff.sort(k, c); }
               catch (Throwable t) { check(G_THROW, false, "Key %s N=%d cutoff=%d: %s", d, n, c, t); continue; }
               check(G_TREE, Key.count == expectTimed && isSorted(k),
                     "%s N=%d cutoff=%d: MergeCutoff compares=%d, expected %d", d, n, c, Key.count, expectTimed);
            }
   }

   static void testStability()
   {
      Random rnd = new Random(20261027);
      for (int nkeys : new int[]{1, 3, 10})
         for (int n = 0; n <= 300; n++)
            for (int c = 1; c <= 70; c++)
            {
               Item[] base = new Item[n];
               for (int i = 0; i < n; i++) base[i] = new Item(rnd.nextInt(nkeys), i);
               Item[] a1 = base.clone(), a2 = base.clone();
               try
               {
                  MergeCutoff.sort(a1, c);
                  counted(a2, c);
               }
               catch (Throwable t)
               {
                  check(G_THROW, false, "Item nkeys=%d N=%d cutoff=%d: %s", nkeys, n, c, t);
                  continue;
               }
               for (Item[] a : new Item[][]{a1, a2})
               {
                  boolean stable = true;
                  boolean[] seen = new boolean[n];
                  boolean perm = true;
                  for (int i = 0; i < n; i++)
                  {
                     if (seen[a[i].idx]) perm = false;
                     seen[a[i].idx] = true;
                     if (i > 0)
                     {
                        if (a[i].key < a[i - 1].key) stable = false;
                        if (a[i].key == a[i - 1].key && a[i].idx < a[i - 1].idx) stable = false;
                     }
                  }
                  String who = (a == a1) ? "MergeCutoff" : "MergeCutoffCounted";
                  check(G_STAB, stable && perm, "%s nkeys=%d N=%d cutoff=%d (stable=%b, perm=%b)",
                        who, nkeys, n, c, stable, perm);
               }
            }
   }

   static void testBadCutoff()
   {
      for (int c : new int[]{0, -1, -7, Integer.MIN_VALUE})
         for (int n : new int[]{0, 1, 2, 10})
         {
            Integer[] a = box(DataGenerator.generate("random", n, 1));
            for (int which = 0; which < 2; which++)
            {
               String who = which == 0 ? "MergeCutoff" : "MergeCutoffCounted";
               Throwable got = null;
               try
               {
                  if (which == 0) MergeCutoff.sort(a.clone(), c);
                  else            MergeCutoffCounted.sort(a.clone(), c);
               }
               catch (Throwable t) { got = t; }
               check(G_CUT, got instanceof IllegalArgumentException,
                     "%s N=%d cutoff=%d: got %s", who, n, c, got);
            }
         }
   }

   /** Nhóm 7, 8: N = 2^k. */
   static void testPowersOfTwo()
   {
      for (String d : DISTS)
         for (int k = 0; k <= 16; k++)
         {
            int n = 1 << k;
            int[] v = DataGenerator.generate(d, n, DataGenerator.seedFor(d, n));
            long[] cnt = counted(box(v), 1);
            long C = cnt[0], S = cnt[3], E = cnt[2];
            long nlg = (long) n * k;
            check(G_CBND, 2 * C >= nlg && C <= nlg, "%s N=2^%d: C=%d, NlgN=%d", d, k, C, nlg);
            check(G_SPOW, S == nlg && E == 0, "%s N=2^%d cutoff=1: S=%d (expect %d), E=%d", d, k, S, nlg, E);
         }
      // cutoff = 2^m, m < k. sorted: mọi m (insertion tuyến tính); random/few_distinct: m <= 6 (đúng tầm lưới)
      for (String d : new String[]{"sorted", "random", "few_distinct"})
         for (int k = 1; k <= 16; k++)
            for (int m = 0; m < k; m++)
            {
               if (!d.equals("sorted") && m > 6) continue;
               int n = 1 << k;
               long[] cnt = counted(box(DataGenerator.generate(d, n, DataGenerator.seedFor(d, n))), 1 << m);
               long expect = (long) n * (k - m);
               check(G_SPOW, cnt[3] == expect, "%s N=2^%d cutoff=2^%d: S=%d, expect %d", d, k, m, cnt[3], expect);
               check(G_AID, cnt[1] == 4 * cnt[3] + 2 * cnt[0] + 4 * cnt[2], "%s N=2^%d cutoff=2^%d", d, k, m);
            }
   }

   /** Toàn mảng là một lá (cutoff = N = k) -> chỉ insertion sort chạy. */
   static void testInsertionAlone()
   {
      for (int k = 1; k <= 50; k++)
      {
         Integer[] s = box(DataGenerator.generate("sorted", k, 0));
         long[] cs = counted(s, k);
         check(G_INS, cs[0] == k - 1 && cs[2] == 0 && cs[1] == 2L * (k - 1) && cs[3] == 0 && isSorted(s),
               "sorted k=%d: C=%d E=%d A=%d S=%d", k, cs[0], cs[2], cs[1], cs[3]);

         Integer[] r = box(DataGenerator.generate("reversed", k, 0));
         long[] cr = counted(r, k);
         long t = (long) k * (k - 1) / 2;
         check(G_INS, cr[0] == t && cr[2] == t && cr[1] == 3L * k * (k - 1) && cr[3] == 0 && isSorted(r),
               "reversed k=%d: C=%d E=%d A=%d S=%d", k, cr[0], cr[2], cr[1], cr[3]);
      }
   }

   // ------------------------------------------------------------------ main

   public static void main(String[] args)
   {
      long t0 = System.nanoTime();
      for (String g : new String[]{G_EA, G_GEN, G_SORT, G_PERM, G_SAME, G_STAB, G_CUT, G_CBND,
                                   G_SPOW, G_SSIM, G_AID, G_EINV, G_INS, G_THROW, G_TREE})
         TALLY.put(g, new long[2]);
      testAssertionsEnabled();
      testGenerator();
      testGrid();
      testStability();
      testBadCutoff();
      testPowersOfTwo();
      testInsertionAlone();

      long totalFail = 0, totalPass = 0;
      System.out.printf("%-66s %8s %5s%n", "GROUP", "PASS", "FAIL");
      for (Map.Entry<String, long[]> e : TALLY.entrySet())
      {
         long[] t = e.getValue();
         totalPass += t[0]; totalFail += t[1];
         System.out.printf("%-66s %8d %5d  %s%n", e.getKey(), t[0], t[1], t[1] == 0 ? "PASS" : "FAIL");
         for (String msg : FAILS.getOrDefault(e.getKey(), List.of())) System.out.println("      - " + msg);
      }
      System.out.printf("%nTOTAL: %d checks, %d failed -> %s  (%.1f s)%n",
                        totalPass + totalFail, totalFail, totalFail == 0 ? "PASS" : "FAIL",
                        (System.nanoTime() - t0) / 1e9);
      System.exit(totalFail == 0 ? 0 : 1);
   }
}
