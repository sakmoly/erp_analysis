"""Re-apply module enablement after build_mobile_config merge fix."""

from erp_analysis.patches.enable_all_phase3_modules import execute as enable_all_modules


def execute():
	enable_all_modules()
