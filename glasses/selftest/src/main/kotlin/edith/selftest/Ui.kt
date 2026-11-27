package edith.selftest

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface

/** Large, legible drawing for 640×480 per eye (scaled for other window sizes). */
class Ui {
    var scale: Float = 1f; private set
    val fg = Color.WHITE
    val accent = Color.rgb(0x40, 0xFF, 0x80)
    val warn = Color.rgb(0xFF, 0xD4, 0x00)
    val bad = Color.rgb(0xFF, 0x30, 0x30)
    val dim = Color.rgb(0x90, 0x90, 0x90)

    val title = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = fg; typeface = Typeface.DEFAULT_BOLD }
    val body = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = fg; typeface = Typeface.DEFAULT }
    val mono = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = fg; typeface = Typeface.MONOSPACE }
    val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 2f; color = fg }
    val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL; color = fg }

    fun applyScale(s: Float) {
        scale = s
        title.textSize = 34f * s; body.textSize = 26f * s; mono.textSize = 20f * s; stroke.strokeWidth = 2f * maxOf(1f, s)
    }

    /** Draws lines top-down from y and returns the next y. Lines wrap to width w. */
    fun lines(c: Canvas, x: Float, y0: Float, w: Float, text: List<String>, p: Paint = body, color: Int = fg): Float {
        var y = y0
        p.color = color
        for (raw in text) {
            for (line in wrap(raw, p, w)) { y += p.textSize * 1.2f; c.drawText(line, x, y, p) }
        }
        p.color = fg
        return y
    }

    private fun wrap(s: String, p: Paint, w: Float): List<String> {
        if (p.measureText(s) <= w) return listOf(s)
        val out = mutableListOf<String>(); var cur = ""
        for (word in s.split(' ')) {
            val t = if (cur.isEmpty()) word else "$cur $word"
            if (p.measureText(t) <= w || cur.isEmpty()) cur = t else { out += cur; cur = word }
        }
        if (cur.isNotEmpty()) out += cur
        return out
    }
}
