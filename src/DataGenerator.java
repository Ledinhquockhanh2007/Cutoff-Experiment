import java.io.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.IntBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Stream;
import java.util.zip.*;

/**
 * Sinh toàn bộ bộ dữ liệu cho thí nghiệm CUTOFF.
 *
 * Kế hoạch (đã chốt):
 *   random                    : 3 thang S = 2^12, 2^16, 2^19, mỗi thang 24 N
 *   sorted, reversed,
 *   nearly_sorted, few_distinct: thang S = 2^16, 24 N
 *   N_j = round(S * 2^(j/24)), j = 0..23 (StrictMath.pow để N giống hệt trên mọi máy)
 *
 * Giá trị (mọi giá trị >= OFFSET = 1_000_000, nằm ngoài Integer cache):
 *   random        : hoán vị ngẫu nhiên của OFFSET..OFFSET+N-1 (Knuth shuffle như bài giảng)
 *   sorted        : OFFSET + i
 *   reversed      : OFFSET + (N-1-i)
 *   nearly_sorted : sorted, rồi floor(N/100) lần đổi chỗ hai vị trí ngẫu nhiên đều, khác nhau
 *   few_distinct  : OFFSET + 1000*k, k ngẫu nhiên đều trong 0..9
 *
 * Seed: seed = 10_000_000 * distId + N, distId = 1..5 theo thứ tự DISTRIBUTIONS.
 *   (N < 10^7 nên mỗi file có seed riêng; sorted/reversed không dùng seed nhưng vẫn ghi.)
 *   Bộ sinh: new java.util.Random(mix64(seed)). java.util.Random có thuật toán cố định trong đặc tả Java,
 *   nên cùng seed cho cùng dãy trên mọi JVM; mix64 (SplitMix64 finalizer) tránh tương quan giữa các seed liền nhau.
 *
 * Định dạng file: int32 little-endian, không header; N = kích thước file / 4.
 *   data/<distribution>/N<7 chữ số>.bin, manifest: data/manifest.csv (distribution,N,seed,file,sha256)
 *
 * Cách dùng (chạy từ thư mục cutoff-experiment):
 *   java -cp build DataGenerator             sinh dữ liệu + manifest + data.zip
 *   java -cp build DataGenerator --verify    kiểm tra sha256 file trên đĩa và sinh lại từ seed
 *   tùy chọn: --out <thư mục> (mặc định data), --no-zip
 */
public final class DataGenerator
{
   public static final int OFFSET = 1_000_000;
   public static final int[] RANDOM_SCALES = {1 << 12, 1 << 16, 1 << 19};
   public static final int OTHER_SCALE = 1 << 16;
   public static final int NS_PER_SCALE = 24;
   public static final List<String> DISTRIBUTIONS =
      List.of("random", "sorted", "reversed", "nearly_sorted", "few_distinct");
   public static final String MANIFEST_HEADER = "distribution,N,seed,file,sha256";

   private DataGenerator() {}

   // ------------------------------------------------------------------ plan

   public record Spec(String dist, int n, long seed)
   {
      public String file() { return dist + "/N" + String.format("%07d", n) + ".bin"; }
   }

   public static long seedFor(String dist, int n)
   {
      int id = DISTRIBUTIONS.indexOf(dist);
      if (id < 0) throw new IllegalArgumentException("unknown distribution: " + dist);
      if (n < 0 || n >= 10_000_000) throw new IllegalArgumentException("N out of range: " + n);
      return 10_000_000L * (id + 1) + n;
   }

   /** 24 giá trị N hình học trong [S, 2S). */
   public static int[] scaleNs(int s)
   {
      int[] ns = new int[NS_PER_SCALE];
      for (int j = 0; j < NS_PER_SCALE; j++)
         ns[j] = (int) Math.round(s * StrictMath.pow(2.0, j / (double) NS_PER_SCALE));
      return ns;
   }

   public static List<Spec> plan()
   {
      List<Spec> specs = new ArrayList<>();
      for (int s : RANDOM_SCALES)
         for (int n : scaleNs(s))
            specs.add(new Spec("random", n, seedFor("random", n)));
      for (String d : DISTRIBUTIONS)
      {
         if (d.equals("random")) continue;
         for (int n : scaleNs(OTHER_SCALE))
            specs.add(new Spec(d, n, seedFor(d, n)));
      }
      return specs;
   }

   // ------------------------------------------------------------------ generation

   static long mix64(long z)
   {
      z = (z ^ (z >>> 30)) * 0xbf58476d1ce4e5b9L;
      z = (z ^ (z >>> 27)) * 0x94d049bb133111ebL;
      return z ^ (z >>> 31);
   }

   public static int[] generate(String dist, int n, long seed)
   {
      Random rnd = new Random(mix64(seed));
      int[] a = new int[n];
      switch (dist)
      {
         case "random" -> {
            for (int i = 0; i < n; i++) a[i] = OFFSET + i;
            for (int i = 0; i < n; i++)                    // Knuth shuffle (bài giảng)
            {
               int r = rnd.nextInt(i + 1);                 // đều trong 0..i
               int t = a[i]; a[i] = a[r]; a[r] = t;
            }
         }
         case "sorted" -> {
            for (int i = 0; i < n; i++) a[i] = OFFSET + i;
         }
         case "reversed" -> {
            for (int i = 0; i < n; i++) a[i] = OFFSET + (n - 1 - i);
         }
         case "nearly_sorted" -> {
            for (int i = 0; i < n; i++) a[i] = OFFSET + i;
            int swaps = n / 100;                           // n >= 100 nên n >= 2, vòng do-while dừng
            for (int t = 0; t < swaps; t++)
            {
               int i = rnd.nextInt(n), j;
               do j = rnd.nextInt(n); while (j == i);
               int x = a[i]; a[i] = a[j]; a[j] = x;
            }
         }
         case "few_distinct" -> {
            for (int i = 0; i < n; i++) a[i] = OFFSET + 1000 * rnd.nextInt(10);
         }
         default -> throw new IllegalArgumentException("unknown distribution: " + dist);
      }
      return a;
   }

   // ------------------------------------------------------------------ I/O

   public static byte[] toBytes(int[] a)
   {
      ByteBuffer bb = ByteBuffer.allocate(4 * a.length).order(ByteOrder.LITTLE_ENDIAN);
      bb.asIntBuffer().put(a);
      return bb.array();
   }

   public static int[] readBin(Path p) throws IOException
   {
      byte[] b = Files.readAllBytes(p);
      if (b.length % 4 != 0) throw new IOException("size not a multiple of 4: " + p);
      IntBuffer ib = ByteBuffer.wrap(b).order(ByteOrder.LITTLE_ENDIAN).asIntBuffer();
      int[] a = new int[ib.remaining()];
      ib.get(a);
      return a;
   }

   static String sha256(byte[] b)
   {
      try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(b)); }
      catch (Exception e) { throw new RuntimeException(e); }
   }

   static long dirSize(Path dir) throws IOException
   {
      try (Stream<Path> s = Files.walk(dir))
      {
         return s.filter(Files::isRegularFile).mapToLong(p -> p.toFile().length()).sum();
      }
   }

   // ------------------------------------------------------------------ modes

   static void generateAll(Path out, boolean zip) throws IOException
   {
      long t0 = System.nanoTime();
      List<Spec> specs = plan();
      StringBuilder manifest = new StringBuilder(MANIFEST_HEADER).append('\n');
      for (Spec s : specs)
      {
         byte[] bytes = toBytes(generate(s.dist(), s.n(), s.seed()));
         Path f = out.resolve(s.file());
         Files.createDirectories(f.getParent());
         Files.write(f, bytes);
         manifest.append(s.dist()).append(',').append(s.n()).append(',').append(s.seed()).append(',')
                 .append(s.file()).append(',').append(sha256(bytes)).append('\n');
      }
      byte[] m = manifest.toString().getBytes(StandardCharsets.UTF_8);   // '\n' cố định, không phụ thuộc OS
      Files.write(out.resolve("manifest.csv"), m);

      long raw = dirSize(out);
      System.out.printf("Generated %d files + manifest.csv in %s (%.1f s)%n",
                        specs.size(), out, (System.nanoTime() - t0) / 1e9);
      System.out.printf("sha256(manifest.csv) = %s%n", sha256(m));
      System.out.printf("data/ size      : %,d bytes (%.1f MB)%n", raw, raw / 1048576.0);
      if (zip)
      {
         Path z = zipDir(out);
         long zs = Files.size(z);
         System.out.printf("%s size: %,d bytes (%.1f MB), %.1f%% of raw%n",
                           z.getFileName(), zs, zs / 1048576.0, 100.0 * zs / raw);
      }
   }

   static Path zipDir(Path out) throws IOException
   {
      Path abs = out.toAbsolutePath().normalize();
      Path z = abs.resolveSibling(abs.getFileName() + ".zip");
      List<Path> files;
      try (Stream<Path> s = Files.walk(abs)) { files = s.filter(Files::isRegularFile).sorted().toList(); }
      try (ZipOutputStream zos = new ZipOutputStream(new BufferedOutputStream(Files.newOutputStream(z))))
      {
         zos.setLevel(Deflater.BEST_COMPRESSION);
         for (Path p : files)
         {
            String name = abs.getParent().relativize(p).toString().replace('\\', '/');
            ZipEntry e = new ZipEntry(name);
            e.setTimeLocal(LocalDateTime.of(2026, 1, 1, 0, 0));   // thời gian cố định -> zip tái lập được
            zos.putNextEntry(e);
            Files.copy(p, zos);
            zos.closeEntry();
         }
      }
      return z;
   }

   /** @return số lỗi */
   static int verify(Path out) throws IOException
   {
      List<String> lines = Files.readAllLines(out.resolve("manifest.csv"), StandardCharsets.UTF_8);
      int fail = 0, ok = 0;
      if (lines.isEmpty() || !lines.get(0).equals(MANIFEST_HEADER))
      {
         System.out.println("FAIL manifest header");
         return 1;
      }
      List<Spec> expected = plan();
      if (lines.size() - 1 != expected.size())
      {
         System.out.printf("FAIL manifest has %d rows, plan has %d%n", lines.size() - 1, expected.size());
         fail++;
      }
      for (int r = 1; r < lines.size(); r++)
      {
         String[] c = lines.get(r).split(",");
         String dist = c[0], file = c[3], sha = c[4];
         int n = Integer.parseInt(c[1]);
         long seed = Long.parseLong(c[2]);
         List<String> errs = new ArrayList<>();
         if (r - 1 < expected.size())
         {
            Spec e = expected.get(r - 1);
            if (!e.dist().equals(dist) || e.n() != n || e.seed() != seed || !e.file().equals(file))
               errs.add("row differs from plan");
         }
         if (seed != seedFor(dist, n)) errs.add("seed != seedFor(dist, N)");
         Path f = out.resolve(file);
         if (!Files.exists(f)) errs.add("file missing");
         else
         {
            byte[] disk = Files.readAllBytes(f);
            if (disk.length != 4L * n) errs.add("file size != 4N");
            if (!sha256(disk).equals(sha)) errs.add("sha256(file on disk) != manifest");
         }
         if (!sha256(toBytes(generate(dist, n, seed))).equals(sha)) errs.add("sha256(regenerated) != manifest");
         if (errs.isEmpty()) ok++;
         else { fail++; System.out.println("FAIL " + file + ": " + String.join("; ", errs)); }
      }
      System.out.printf("verify: %d OK, %d FAIL%n", ok, fail);
      return fail;
   }

   public static void main(String[] args) throws IOException
   {
      Path out = Paths.get("data");
      boolean verify = false, zip = true;
      for (int i = 0; i < args.length; i++)
      {
         switch (args[i])
         {
            case "--verify" -> verify = true;
            case "--no-zip" -> zip = false;
            case "--out"    -> out = Paths.get(args[++i]);
            default -> { System.err.println("unknown argument: " + args[i]); System.exit(2); }
         }
      }
      if (verify) System.exit(verify(out) == 0 ? 0 : 1);
      generateAll(out, zip);
   }
}
