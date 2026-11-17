package bench;

import org.openjdk.jmh.annotations.*;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.IntBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.concurrent.TimeUnit;

/**
 * JMH benchmark for MergeCutoff cross-validation (T08 / §5 hợp đồng).
 */
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 10, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(3)
@State(Scope.Thread)
public class MergeCutoffBenchmark
{
   @Param({"4096", "65536", "524288"})
   public int n;

   @Param({"1", "7", "10", "30"})
   public int cutoff;

   private Sorter sorter;
   private Integer[] base;
   private Integer[] array;

   static int[] readBin(Path p) throws IOException
   {
      byte[] b = Files.readAllBytes(p);
      IntBuffer ib = ByteBuffer.wrap(b).order(ByteOrder.LITTLE_ENDIAN).asIntBuffer();
      int[] a = new int[ib.remaining()];
      ib.get(a);
      return a;
   }

   @Setup(Level.Trial)
   public void setupTrial() throws Exception
   {
      sorter = (Sorter) Class.forName("MergeCutoffBridge").getDeclaredConstructor().newInstance();
      Path p = Paths.get(String.format("data_run5/random/N%07d.bin", n));
      int[] v = readBin(p);
      base = new Integer[v.length];
      for (int i = 0; i < v.length; i++) base[i] = Integer.valueOf(v[i]);
   }

   @Setup(Level.Invocation)
   public void setupInvocation()
   {
      array = base.clone();
   }

   @Benchmark
   public Integer[] sort()
   {
      sorter.sort(array, cutoff);
      return array;
   }
}
