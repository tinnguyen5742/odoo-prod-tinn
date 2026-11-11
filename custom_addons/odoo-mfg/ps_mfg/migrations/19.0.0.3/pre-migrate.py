"""Backfill ps.mfg.wip.period_date from month/year before the field swap.

The month/year Integer pair is replaced by a single period_date (first day
of month). The old UNIQUE(company, account, month, year) maps 1:1 onto
UNIQUE(company, account, period_date), so backfilling first-of-month keeps
existing rows constraint-safe.
"""


def migrate(cr, version):
    cr.execute("SELECT to_regclass('public.ps_mfg_wip')")
    if not cr.fetchone()[0]:
        return
    cr.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'ps_mfg_wip' AND column_name = 'period_date'"
    )
    if cr.fetchone() is None:
        cr.execute("ALTER TABLE ps_mfg_wip ADD COLUMN period_date DATE")
    cr.execute(
        """
        UPDATE ps_mfg_wip
        SET period_date = make_date(
            GREATEST(COALESCE(year, 2000), 1),
            GREATEST(LEAST(COALESCE(month, 1), 12), 1), 1)
        WHERE period_date IS NULL
        """
    )
