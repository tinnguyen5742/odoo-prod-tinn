# PATSOFT eLearning Analytics & Reports - Odoo 19

GitHub repository: [patsoft-extra/ps_elearning_analytics](https://github.com/patsoft-extra/ps_elearning_analytics).

The Odoo technical addon name remains `ps_elearning_report`. Keep this directory name when installing so the module identifiers and references resolve correctly.

This installable addon is limited to eLearning reports. It does not enroll learners, configure course policies, schedule reminders, create Discuss channels, or write certification records to employee resumes.

| Report | Odoo menu |
| --- | --- |
| Course summary | eLearning > Courses > open a course > Print |
| Course overview | eLearning > Courses > select courses > Print |
| Course progress | eLearning > Courses > open a course > Print |
| HR training progress | eLearning > Courses > select courses > Print; also available as list/pivot/graph |

Both progress PDFs use landscape A4. They show learner progress and, when available, enrollment date, last update, and next lesson. The HR report also includes employee department/job information when linked to an employee. The learner email is omitted.

Report actions render PDFs on demand from current Odoo records. The `pdf/` folder contains review copies exported from the Odoo test instance; they are not loaded as Odoo data by this addon and reflect the selected test records.

## Scope

- Four QWeb PDF actions: course summary, course overview, per-course progress, and multi-course HR progress.
- A read-only SQL view for employee progress with list, pivot, graph, and search filters.
- Enrollment employee linkage and a deadline field used by the report. This addon does not assign deadlines or run deadline reminders.

## Installation

Clone the repository into a directory named `ps_elearning_report`:

```bash
git clone https://github.com/patsoft-extra/ps_elearning_analytics.git ps_elearning_report
```

Then:

1. Make the `ps_elearning_report` directory available on the Odoo `addons_path`.
2. Install `website_slides` and `hr`.
3. Update the Apps list and install **PATSOFT eLearning Reports**.
4. Assign **eLearning HR Manager** to HR users who need company-wide progress and access to the multi-course PDF.

The post-install hook registers the three legacy QWeb templates from `templates/`. The HR progress template and report actions are loaded as addon data.

## Access

The progress analysis is read-only. Internal users see their own enrollment records, eLearning officers see records for courses they manage, and the eLearning HR Manager group can review all progress. Review access assignments on staging before deployment.

## Test-instance PDF copies

- `pdf/elearning_course_summary.pdf`: course 7, “Training nhân viên mới”.
- `pdf/elearning_courses_overview.pdf`: courses 7 and 8.
- `pdf/elearning_course_progress.pdf`: course 7, “Training nhân viên mới”.

Both test accounts exposed these three report actions. The HR progress action was not available on the test instance, so no PDF copy was exported for it. The addon does not provide certificate files.

See [requirement coverage](docs/REQUIREMENT_COVERAGE.md) and [Odoo installation notes](docs/SETUP_ODOO_WEB.md). Run the addon tests from an Odoo 19 test database with:

```powershell
odoo --stop-after-init --test-enable -i ps_elearning_report -d <test_database>
```
