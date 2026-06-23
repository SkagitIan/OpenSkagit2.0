from django.test import SimpleTestCase

from .services import parse_statement


class TaxStatementParserTests(SimpleTestCase):
    def test_parse_statement_captures_delinquent_table_rows(self):
        html = """
        <table><tr><td>Parcel ID: P106555</td></tr></table>
        <h3>2026 Real Estate Tax Statement</h3>
        <div id="divDelinquent">
          <table id="tblDelinquent">
            <tr><th>Year</th><th>Taxes</th><th>Interest</th><th>Penalty</th><th>Total</th></tr>
            <tr><td>2026</td><td>$2,816.67</td><td>$84.35</td><td>$0.00</td><td>$2,901.02</td></tr>
            <tr><td>2025</td><td>$4,962.93</td><td>$520.07</td><td>$0.00</td><td>$5,483.00</td></tr>
            <tr><td>2024</td><td>$2,161.58</td><td>$323.49</td><td>$0.00</td><td>$2,485.07</td></tr>
            <tr><td colspan="4">Delinquent Taxes, Interest, and Penalty TOTAL</td><td>$10,869.09</td></tr>
          </table>
        </div>
        <b>2026 Total Due:</b> $5,712.62
        <b>2026 Amount Paid:</b> $0.00
        """
        parsed = parse_statement(html, "https://example.test", today=None)

        self.assertEqual([row["year"] for row in parsed["delinquent_rows"]], [2026, 2025, 2024])
        self.assertEqual(parsed["delinquent_rows"][0]["total"], "2901.02")
