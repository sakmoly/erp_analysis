-- Materialized into tabSalesDashBoard: same net/cost grain as Printechs Gross Profit (ViewSalesGrossProfit).
CREATE OR REPLACE VIEW `ViewSalesDashBoardFromSI` AS
SELECT
	`Territory`,
	`Warehouse`,
	`Invoice Date` AS `Invoice_Date`,
	`Invoice No` AS `Invoice_No`,
	`Doc Status` AS `Doc_Status`,
	`UOM`,
	`Item Code` AS `Item_Code`,
	`Description`,
	`Division`,
	`Sub Group` AS `Sub_Group`,
	`Brand`,
	`Customer`,
	`Sales Person` AS `Sales_Person`,
	`Qty` AS `Sold_Qty`,
	`SOH Qty` AS `SOH_Qty`,
	`Gross Amt` AS `Gross_Amount`,
	`Global Disc Amt` AS `Global_Disc Amount`,
	`Line Disc Amt` AS `Line_Disc_Amount`,
	`Net Amount` AS `Net_Amount`,
	`VAT Amt` AS `VAT_Amount`,
	`Amt W/VAT` AS `Amount_W_VAT`,
	`Cost` AS `COGS`,
	`is_product_bundle`,
	`Company`,
	`SI_Detail_Name`,
	`Bundle_Parent_Item`,
	`PBI_Name`
FROM (
	SELECT
		si.`territory` AS `Territory`,
		v.`warehouse` AS `Warehouse`,
		v.`posting_date` AS `Invoice Date`,
		v.`invoice_no` AS `Invoice No`,
		si.`docstatus` AS `Doc Status`,
		v.`uom` AS `UOM`,
		v.`item_code` AS `Item Code`,
		LEFT(v.`description`, 500) AS `Description`,
		v.`item_main_group_name` AS `Division`,
		v.`item_sub_group_name` AS `Sub Group`,
		COALESCE(sit.`brand`, '') AS `Brand`,
		v.`customer` AS `Customer`,
		COALESCE(v.`sales_person`, '') AS `Sales Person`,
		v.`qty` AS `Qty`,
		v.`stock_qty` AS `SOH Qty`,
		COALESCE(v.`gross_amout`, 0) AS `Gross Amt`,
		CASE
			WHEN v.`idx` = 1 THEN COALESCE(v.`discount_amount_total`, 0)
			ELSE COALESCE(si.`discount_amount`, 0) * (v.`net_amount` * 100 / NULLIF(si.`base_net_total`, 0)) / 100
		END AS `Global Disc Amt`,
		COALESCE(v.`discount_amt`, 0) * v.`qty` AS `Line Disc Amt`,
		v.`net_amount` AS `Net Amount`,
		v.`tax_amount` AS `VAT Amt`,
		v.`amount_with_tax` AS `Amt W/VAT`,
		v.`cost` AS `Cost`,
		v.`is_product_bundle` AS `is_product_bundle`,
		si.`company` AS `Company`,
		v.`name` AS `SI_Detail_Name`,
		CASE WHEN v.`is_product_bundle` = 1 THEN v.`item_code` ELSE '' END AS `Bundle_Parent_Item`,
		'' AS `PBI_Name`
	FROM `ViewSalesGrossProfit` v
	INNER JOIN `tabSales Invoice` si ON si.`name` = v.`invoice_no` AND si.`docstatus` = 1
	LEFT JOIN `tabSales Invoice Item` sit ON sit.`name` = v.`name`
) AS `src`;
