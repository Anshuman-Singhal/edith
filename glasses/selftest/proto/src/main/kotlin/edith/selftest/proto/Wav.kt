package edith.selftest.proto

import java.io.File
import java.io.RandomAccessFile

/** Minimal streaming 16-bit PCM WAV writer (header patched on close). */
class WavWriter(file: File, private val rate: Int, private val channels: Int) : AutoCloseable {
    private val raf = RandomAccessFile(file, "rw").apply { setLength(0); write(ByteArray(44)) }
    var samples = 0L; private set

    fun write(buf: ShortArray, off: Int, len: Int) {
        val b = ByteArray(len * 2)
        for (i in 0 until len) { val v = buf[off + i].toInt(); b[2 * i] = v.toByte(); b[2 * i + 1] = (v shr 8).toByte() }
        raf.write(b); samples += len
    }

    override fun close() {
        val data = samples * 2
        raf.seek(0)
        fun s(x: String) = raf.write(x.toByteArray(Charsets.US_ASCII))
        fun i32(x: Long) { for (k in 0 until 4) raf.write(((x shr (8 * k)) and 0xff).toInt()) }
        fun i16(x: Int) { raf.write(x and 0xff); raf.write((x shr 8) and 0xff) }
        s("RIFF"); i32(36 + data); s("WAVE"); s("fmt "); i32(16); i16(1); i16(channels)
        i32(rate.toLong()); i32(rate.toLong() * channels * 2); i16(channels * 2); i16(16); s("data"); i32(data)
        raf.close()
    }
}

/** Little-endian bytes of 16-bit PCM. */
internal fun pcmBytes(buf: ShortArray, off: Int, len: Int): ByteArray {
    val b = ByteArray(len * 2)
    for (i in 0 until len) { val v = buf[off + i].toInt(); b[2 * i] = v.toByte(); b[2 * i + 1] = (v shr 8).toByte() }
    return b
}
