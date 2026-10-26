-- Used by Printechs Gross Profit (get_bundle_item_data_db). Missing on some sites.
CREATE OR REPLACE VIEW `ViewBundle` AS
SELECT
	pit.`parent_detail_docname` AS `parent_detail_docname`,
	pit.`parent` AS `delivery_note`,
	pit.`item_code` AS `item_code`,
	pit.`item_name` AS `description`,
	pit.`qty` AS `qty`,
	COALESCE(ABS(sle.`actual_qty`), pit.`qty`) AS `actual_qty`,
	CASE
		WHEN sle.`actual_qty` IS NULL OR sle.`actual_qty` = 0 THEN COALESCE(pit.`incoming_rate`, 0)
		ELSE ABS(sle.`stock_value_difference` / sle.`actual_qty`)
	END AS `cost`,
	pit.`rate_percentage` AS `rate_percentage`,
	pit.`name` AS `bundle_row_name`,
	pit.`idx` AS `idx`
FROM `tabPacked Item` pit
LEFT JOIN `tabStock Ledger Entry` sle ON sle.`voucher_no` = pit.`parent`
	AND sle.`voucher_detail_no` = pit.`parent_detail_docname`
	AND sle.`item_code` = pit.`item_code`
	AND sle.`voucher_type` = 'Delivery Note'
	AND sle.`is_cancelled` = 0
	AND sle.`actual_qty` < 0
WHERE pit.`parenttype` = 'Delivery Note'
	AND pit.`docstatus` = 1;
