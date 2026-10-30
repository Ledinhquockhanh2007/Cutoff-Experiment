import com.sun.management.ThreadMXBean;
import org.openjdk.jol.info.ClassLayout;
import org.openjdk.jol.info.GraphLayout;
import org.openjdk.jol.vm.VM;

import java.io.File;
import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

public class MemoryProbe {

    private static final ThreadMXBean threadBean =
            (ThreadMXBean) ManagementFactory.getThreadMXBean();

    static {
        if (threadBean.isThreadAllocatedMemorySupported() && !threadBean.isThreadAllocatedMemoryEnabled()) {
            threadBean.setThreadAllocatedMemoryEnabled(true);
        }
    }

    public static int[] loadInts(Path path, int n) throws IOException {
        byte[] bytes = Files.readAllBytes(path);
        if (bytes.length < n * 4) {
            throw new IllegalArgumentException("File " + path + " has " + bytes.length + " bytes, expected at least " + (n * 4));
        }
        int[] a = new int[n];
        ByteBuffer.wrap(bytes, 0, n * 4).order(ByteOrder.LITTLE_ENDIAN).asIntBuffer().get(a);
        return a;
    }

    public static void printClassLayouts() {
        System.out.println("=== VM DETAILS ===");
        System.out.println(VM.current().details());

        System.out.println("=== ClassLayout: Integer ===");
        System.out.println(ClassLayout.parseClass(Integer.class).toPrintable());

        System.out.println("=== ClassLayout: Integer[] ===");
        System.out.println(ClassLayout.parseClass(Integer[].class).toPrintable());

        System.out.println("=== ClassLayout: Comparable[] ===");
        System.out.println(ClassLayout.parseClass(Comparable[].class).toPrintable());
    }

    public static void checkIdentity(String dataDirStr) throws IOException {
        Path dataDir = Path.of(dataDirStr);
        String[] dists = {"random", "sorted", "reversed", "nearly_sorted", "few_distinct"};
        int n = 65536;
        System.out.println("distribution,N,total_elements,distinct_identities,all_distinct");
        for (String dist : dists) {
            Path file = dataDir.resolve(dist).resolve("N0065536.bin");
            if (!Files.exists(file)) {
                System.err.println("File not found: " + file);
                continue;
            }
            int[] raw = loadInts(file, n);
            Integer[] a = new Integer[n];
            for (int i = 0; i < n; i++) {
                a[i] = Integer.valueOf(raw[i]);
            }
            Set<Integer> identitySet = Collections.newSetFromMap(new IdentityHashMap<>());
            identitySet.addAll(Arrays.asList(a));
            boolean allDistinct = (identitySet.size() == n);
            System.out.printf("%s,%d,%d,%d,%b%n", dist, n, a.length, identitySet.size(), allDistinct);
        }
    }

    public static class MeasurementResult {
        public int n;
        public long jolArrayASize;
        public long jolArrayAuxSize;
        public long jolIntsTotal;
        public long jolAAndIntegers;
        public long jolTotal; // a + aux + integers

        public long allocArrayA;
        public long allocIntegers;
        public long allocAux;
        public long allocTotal;
    }

    private static void warmup(int[] rawInts) {
        int wN = Math.min(rawInts.length, 1024);
        Integer[] wA = new Integer[wN];
        for (int i = 0; i < wN; i++) {
            wA[i] = Integer.valueOf(rawInts[i]);
        }
        Integer[] copy = Arrays.copyOf(wA, wN);
        MergeCutoff.sort(copy, 30);
    }

    public static MeasurementResult measureSingle(int n, int[] rawInts) {
        long threadId = Thread.currentThread().threadId();

        // Step 1: ThreadMXBean allocation for array a
        System.gc();
        long t0 = threadBean.getThreadAllocatedBytes(threadId);
        Integer[] a = new Integer[n];
        long t1 = threadBean.getThreadAllocatedBytes(threadId);
        long allocA = t1 - t0;

        // Step 2: ThreadMXBean allocation for boxing Integers
        long t2 = threadBean.getThreadAllocatedBytes(threadId);
        for (int i = 0; i < n; i++) {
            a[i] = Integer.valueOf(rawInts[i]);
        }
        long t3 = threadBean.getThreadAllocatedBytes(threadId);
        long allocInts = t3 - t2;

        // Step 3: ThreadMXBean allocation for MergeCutoff.sort(copy, 30) -> aux
        Integer[] copy = Arrays.copyOf(a, n);
        System.gc();
        long t4 = threadBean.getThreadAllocatedBytes(threadId);
        MergeCutoff.sort(copy, 30);
        long t5 = threadBean.getThreadAllocatedBytes(threadId);
        long allocAux = t5 - t4;

        MeasurementResult res = new MeasurementResult();
        res.n = n;
        res.allocArrayA = allocA;
        res.allocIntegers = allocInts;
        res.allocAux = allocAux;
        res.allocTotal = allocA + allocInts + allocAux;

        // JOL measurements
        Comparable[] aux = new Comparable[n];
        res.jolArrayASize = ClassLayout.parseInstance(a).instanceSize();
        res.jolArrayAuxSize = ClassLayout.parseInstance(aux).instanceSize();
        res.jolAAndIntegers = GraphLayout.parseInstance((Object) a).totalSize();
        res.jolIntsTotal = res.jolAAndIntegers - res.jolArrayASize;
        res.jolTotal = GraphLayout.parseInstance((Object) a, (Object) aux).totalSize();

        return res;
    }

    public static void runProbe(int n, String filePath, int repetitions) throws IOException {
        Path path = Path.of(filePath);
        int[] raw = loadInts(path, n);

        // Warmup before measurement
        warmup(raw);

        // Run repetitions
        List<MeasurementResult> results = new ArrayList<>();
        for (int r = 0; r < repetitions; r++) {
            results.add(measureSingle(n, raw));
        }

        // Sort by allocTotal and take median
        results.sort(Comparator.comparingLong(m -> m.allocTotal));
        MeasurementResult med = results.get(repetitions / 2);

        System.out.printf("RESULT:%d,%d,%d,%d,%d,%d,%d,%d,%d,%d%n",
                med.n,
                med.jolArrayASize,
                med.jolArrayAuxSize,
                med.jolIntsTotal,
                med.jolAAndIntegers,
                med.jolTotal,
                med.allocArrayA,
                med.allocIntegers,
                med.allocAux,
                med.allocTotal
        );
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            System.out.println("Usage: MemoryProbe <layouts|identity|probe> [args...]");
            return;
        }

        String mode = args[0];
        if ("layouts".equalsIgnoreCase(mode)) {
            printClassLayouts();
        } else if ("identity".equalsIgnoreCase(mode)) {
            String dataDir = args.length > 1 ? args[1] : "data";
            checkIdentity(dataDir);
        } else if ("probe".equalsIgnoreCase(mode)) {
            int n = Integer.parseInt(args[1]);
            String filePath = args[2];
            int reps = args.length > 3 ? Integer.parseInt(args[3]) : 3;
            runProbe(n, filePath, reps);
        } else {
            System.err.println("Unknown mode: " + mode);
        }
    }
}
