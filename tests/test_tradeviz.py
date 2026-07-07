"""Offline tests for the trade-detail viz (pure; no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elp.tradeviz import svg_line  # noqa: E402


class TestSvg(unittest.TestCase):
    def test_line_renders_polyline_and_entry_marker(self):
        svg = svg_line([{"pts": [(0, 1.0), (1, 2.0), (2, 1.5)], "cls": "pv", "dash": False}],
                       entry_idx=1)
        self.assertIn("<svg", svg)
        self.assertIn("<polyline", svg)
        self.assertIn('class="pv"', svg)
        self.assertIn("class=entry", svg)          # vertical entry marker

    def test_dashed_series_has_dasharray(self):
        svg = svg_line([{"pts": [(0, 1.0), (1, 1.1)], "cls": "hyp", "dash": True}])
        self.assertIn("stroke-dasharray", svg)

    def test_empty_is_placeholder(self):
        self.assertIn("no data", svg_line([{"pts": [], "cls": "x", "dash": False}]))

    def test_candles_draw_up_and_down_bodies_with_wicks(self):
        from datetime import date
        from elp.tradeviz import svg_candles
        # bar 0 up (c>o), bar 1 down (c<o)
        bars = [(date(2026, 7, 6), 100.0, 105.0, 99.0, 104.0, 1e6),
                (date(2026, 7, 7), 104.0, 106.0, 98.0, 99.0, 1e6)]
        svg = svg_candles(bars, entry_idx=0, dates=[b[0] for b in bars])
        self.assertIn("<rect", svg)              # bodies
        self.assertIn("class=up", svg)           # up day
        self.assertIn("class=down", svg)         # down day
        self.assertIn("class=wick", svg)         # wicks
        self.assertIn("Jul 07", svg)             # date axis still present
        self.assertIn("no data", svg_candles([]))  # empty -> placeholder

    def test_dashed_gridlines_and_end_dot(self):
        from datetime import date
        dts = [date(2026, 6, 24), date(2026, 6, 29), date(2026, 7, 6)]
        svg = svg_line([{"pts": [(0, 1.0), (1, 2.0), (2, 1.5)], "cls": "leg", "dash": False}],
                       entry_idx=1, dates=dts)
        self.assertIn("class=grid", svg)          # dashed vertical guides
        self.assertIn("<circle", svg)             # latest-value dot
        self.assertIn(">entry<", svg)             # entry marker label

    def test_date_axis_labels_first_and_last_dates(self):
        from datetime import date
        dts = [date(2026, 6, 24), date(2026, 6, 29), date(2026, 7, 1), date(2026, 7, 6)]
        svg = svg_line([{"pts": [(i, float(i)) for i in range(4)], "cls": "leg", "dash": False}],
                       dates=dts)
        self.assertIn("Jun 24", svg)          # first tick
        self.assertIn("Jul 06", svg)          # last tick
        self.assertNotIn("Jun 24", svg_line([{"pts": [(0, 1.0), (1, 2.0)], "cls": "leg", "dash": False}]))  # no dates -> no axis

    def test_tags_self_close_polyline_is_direct_svg_child(self):
        # Regression: unquoted `fill=none/>` / `class=entry/>` swallowed the slash, so tags did
        # not self-close and the <polyline> nested inside <line> (a non-container -> not rendered).
        from html.parser import HTMLParser

        class _Tree(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.stack, self.parent_of, self.attrs_of = [], {}, {}

            def handle_starttag(self, tag, attrs):
                self.parent_of.setdefault(tag, self.stack[-1] if self.stack else None)
                self.attrs_of.setdefault(tag, dict(attrs))
                self.stack.append(tag)

            def handle_startendtag(self, tag, attrs):   # properly self-closed -> no nesting
                self.parent_of.setdefault(tag, self.stack[-1] if self.stack else None)
                self.attrs_of.setdefault(tag, dict(attrs))

            def handle_endtag(self, tag):
                while self.stack and self.stack[-1] != tag:
                    self.stack.pop()
                if self.stack:
                    self.stack.pop()

        svg = svg_line([{"pts": [(0, -1.0), (1, 2.0), (2, 1.5)], "cls": "pv", "dash": False}],
                       entry_idx=1)   # forces both a zero-axis <line> and an entry <line>
        t = _Tree()
        t.feed(svg)
        self.assertEqual(t.parent_of.get("polyline"), "svg")   # sibling of <line>, not its child
        self.assertEqual(t.attrs_of["polyline"].get("fill"), "none")   # not "none/"
        self.assertEqual(t.attrs_of["line"].get("class"), "axis")      # not "axis/"


from datetime import date  # noqa: E402

from elp.tradeviz import combined_series, leg_price_series  # noqa: E402


def _idea(entry, p_ticker="GILD", n_ticker="VC"):
    return {"supplier": "GILD", "customer": "CAH", "side": 1, "expression": "stock-pair",
            "entry": entry,
            "primary": {"role": "primary", "ticker": p_ticker, "direction": 1, "instrument": "stock",
                        "notional": 200000.0, "entry_px": 100.0},
            "neutralizer": {"role": "neutralizer", "ticker": n_ticker, "direction": -1,
                            "instrument": "stock", "notional": 200000.0, "entry_px": 50.0}}


class TestSeries(unittest.TestCase):
    def test_combined_splits_at_entry_and_matches_idea_return(self):
        # entry on the middle day; GILD rises 90->100->110, VC flat 50
        bars = {"GILD": [(date(2026, 6, 1), 90.0, 1e6), (date(2026, 6, 2), 100.0, 1e6),
                         (date(2026, 6, 3), 110.0, 1e6)],
                "VC": [(date(2026, 6, 1), 50.0, 1e6), (date(2026, 6, 2), 50.0, 1e6),
                       (date(2026, 6, 3), 50.0, 1e6)]}
        cs = combined_series(_idea("2026-06-02"), bars)
        # pre-entry (day 0) is dashed and negative (GILD 90 vs entry ref 100)
        self.assertAlmostEqual(cs["dashed"][0][1], -0.10, places=6)
        self.assertEqual(cs["entry_idx"], 1)
        self.assertAlmostEqual(cs["solid"][-1][1], 0.10, places=6)   # day 2: +10% long leg, VC flat

    def test_leg_price_series_stock_is_prices(self):
        bars = [(date(2026, 6, 1), 90.0, 1e6), (date(2026, 6, 2), 100.0, 1e6)]
        leg = {"ticker": "GILD", "direction": 1, "instrument": "stock", "entry_px": 100.0}
        self.assertEqual(leg_price_series(leg, bars, date(2026, 6, 2)), [(0, 90.0), (1, 100.0)])

    def test_leg_price_series_spread_reprices(self):
        bars = [(date(2026, 6, 1), 100.0, 1e6), (date(2026, 6, 10), 95.0, 1e6)]
        leg = {"ticker": "PG", "direction": -1, "instrument": "spread", "notional": 2e5,
               "entry_px": 100.0, "S0": 100.0, "k_long": 100.0, "k_short": 90.0,
               "T0": 45 / 365.0, "iv": 0.3, "dte": 45}
        s = leg_price_series(leg, bars, date(2026, 6, 1))
        self.assertEqual(len(s), 2)
        self.assertTrue(all(isinstance(y, float) for _, y in s))


from elp.tradeviz import PAGE_CSS, trade_detail_html  # noqa: E402


class TestDetailHtml(unittest.TestCase):
    def _bars(self):
        return {"GILD": [(date(2026, 6, 1), 90.0, 1e6), (date(2026, 6, 2), 100.0, 1e6),
                         (date(2026, 6, 3), 110.0, 1e6)],
                "VC": [(date(2026, 6, 1), 50.0, 1e6), (date(2026, 6, 2), 50.0, 1e6),
                       (date(2026, 6, 3), 50.0, 1e6)]}

    def test_block_has_header_charts_and_table(self):
        html = trade_detail_html(_idea("2026-06-02"), self._bars())
        self.assertIn("LONG GILD", html)
        self.assertIn("vs CAH", html)
        self.assertIn("<svg", html)                 # at least one chart
        self.assertIn("combined", html.lower())     # combined section / label
        self.assertIn("Grade-C", html)              # honest caveat

    def test_missing_bars_is_fail_soft(self):
        html = trade_detail_html(_idea("2026-06-02"), {"GILD": [], "VC": []})
        self.assertIn("no price data", html)        # leg note, no crash

    def test_page_css_is_nonempty_string(self):
        self.assertIsInstance(PAGE_CSS, str)
        self.assertIn("svg.chart", PAGE_CSS)

    def test_pair_neutralizer_size_not_mislabeled(self):
        html = trade_detail_html(_idea("2026-06-02"), self._bars())
        self.assertNotIn("β-hedge", html)   # stock-pair neutralizer -> "pair", not hedge


if __name__ == "__main__":
    unittest.main()
