"""Base class for Excel writers."""


class ExcelFormatterBase:
    """Base behaviors shared by Excel writer implementations."""

    def format(self, workbook):
        """Apply formatting rules to ``workbook``.

        TODO: Provide helper utilities for column sizing, number formats, and style sheets.
        """
        pass
