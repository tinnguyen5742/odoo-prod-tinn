# PatSoft CRM Real Estates

Property commission defaults and metric display labels for
`dev_property_management` on Odoo 19.

## Commission defaults

- Property and Sub Property forms provide Commission Type (Fixed or Percentage),
  Fixed Amount, and Percentage, matching Agent Commission.
- Selecting a parent property copies its commission settings to the sub property.
- New sub properties, including generated units, inherit missing commission values
  from their parent.
- Agent commissions take defaults from the property linked to their booking or
  tenancy. A linked sub property supplies its own settings; a directly linked
  parent property supplies the parent's settings.
- All copied values remain editable. Later changes to a parent or sub property do
  not update existing sub properties or commissions.
- Explicit values passed when creating records, including zero amounts or
  percentages, take precedence over inherited defaults.

## Sub property area and dimensions

- The Sub Property form shows “Diện tích và kích thước” directly below Agent
  Commission, with Length x Width on its own row, followed by three columns
  for direction and frontages; land, construction and usable areas; and road
  and alley dimensions.
- Length and width use separate numeric inputs. All measurements are editable
  decimal values in metres or square metres, and direction uses the existing
  Facing field.
- The direction dropdown in this section is limited to eight predefined values:
  East, West, South, North, Northeast, Southeast, Northwest, and Southwest.
  Direction names support Vietnamese translations from `i18n/vi.po`. Users
  cannot create or edit directions from this dropdown. Module upgrades update
  existing predefined directions to the English source names.
- These measurements are entered independently and do not recalculate Total Size
  or Carpet Area.

## CRM consultation calls

- Lead and Opportunity forms show a separate Consultation Calls tab immediately
  after Notes and before Contacts, with an editable table containing Start Date (date and time),
  Result, and Notes columns.
- All three values are entered manually, without automatic dates or results.
- Results include Wrong Phone Number, Information Unchanged, No Answer, Sold,
  Price Reduced, Busy, and Temporarily Suspended. Sales users can create new
  results from the dropdown; sales managers can also edit or delete unused results.
- Call records follow access to their linked leads and are deleted with the lead.
- Labels and predefined results use English source text with Vietnamese
  translations in `i18n/vi.po`.

## Consultation calls dashboard

- Property Management → Dashboard → Consultation Calls Dashboard shows one row
  per accessible CRM lead or opportunity with a dated consultation call.
- The latest Start Date (including time) determines the call shown. Calls without
  a Start Date are excluded; equal timestamps use the most recently created call.
- Columns show the CRM title, linked property's owner, latest call result,
  Completed status in green, latest call start date and time, and CRM salesperson.
- Rows are ordered by the latest call first. Opening a row opens its CRM record.
  Search, date filters, My Calls, and grouping by salesperson or start date are available.
- Adding, changing, or deleting calls updates the dashboard automatically.
  CRM access rules still apply, and dashboard rows cannot be edited directly.
- Start Date uses the user's timezone. On module upgrade, existing date-only
  values become datetimes at midnight UTC; their original time was not recorded.

## Metric display labels

- Total Size and Carpet Area display `sq.m2.` on properties, booking wizards,
  property PDFs, the portal, and the website, including price per area labels.
- Length, Width, and Height display `m`.
- Only display labels change. Existing values, technical field names such as
  `total_square_foot`, calculations, and database columns remain unchanged.

The module depends on `dev_property_management` and inherits its models and
templates without modifying the original module.

## Vietnamese translations

- `i18n/vi.po` provides the Vietnamese property terminology for
  `dev_property_management` and the commission fields added by this module.
- The parent relationship is “Bất động sản cha”; the Parent Property purpose
  selection is “Tài sản cấp cha”. Both Vietnamese language codes `vi` and `vi_VN`
  use this catalog through Odoo's language fallback.
- Metric labels include the current `sq.m.` labels and older spellings.
- Shared JavaScript controls and dashboard strings use their original modules'
  translations through Odoo's standard translation loading.
- Activate Vietnamese and select it in the user's preferences. Restart Odoo and
  upgrade `ps_crm_real_estates` with `--i18n-overwrite` to replace existing
  translations, then reload the browser.

## Installation

Include `custom_addons/odoo-sale` in `addons_path`, restart Odoo, and update the
Apps List. Remove the Apps filter, search for `ps_crm_real_estates`, and install it.
Upgrade the module after adding fields or changing its XML views.
When existing translations still show imperial units, upgrade this module with
`--i18n-overwrite` to replace those labels using its metric translation files.
