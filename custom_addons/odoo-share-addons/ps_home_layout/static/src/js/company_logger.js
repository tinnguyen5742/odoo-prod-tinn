import { WebClient } from "@web/webclient/webclient";
import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";

function injectThemeColor(color) {
  if (!color) return;

  let styleTag = document.getElementById("ps_theme_custom_style");
  if (!styleTag) {
    styleTag = document.createElement("style");
    styleTag.id = "ps_theme_custom_style";
    document.head.appendChild(styleTag);
  }

  styleTag.innerHTML = `
        /* 1. ROOT & GENERAL VARIABLES */
        :root, [data-bs-theme="light"], body {
            --o-brand-odoo: ${color} !important;
            --o-brand-primary: ${color} !important;
            --primary: ${color} !important;
            --o-color-1: ${color} !important;
            --o-navbar-bg: ${color} !important;
            --NavBar-background-color: ${color} !important;
            --bs-primary: ${color} !important;
            --bs-primary-rgb: ${color} !important;
            --link-color: ${color} !important;
            --link-hover-color: ${color} !important;
        }

        /* 2. NAVBAR TOP */
        .o_main_navbar, header.o_navbar, nav.o_main_navbar {
            background-color: ${color} !important;
        }

        /* 3. BUTTON PRIMARY (Nút filled) */
        .btn-primary {
            background-color: ${color} !important;
            border-color: ${color} !important;
            color: #ffffff !important;
        }

        /* 4. BUTTON OUTLINE (Nút New, nút viền màu Theme) */
        .btn-outline-primary,
        .btn-secondary.o_control_panel_main_buttons,
        .o_control_panel .btn-outline-primary,
        .o_form_button_create {
            color: ${color} !important;
            border-color: ${color} !important;
            background-color: transparent !important;
        }

        .btn-outline-primary:hover,
        .btn-outline-primary:active,
        .btn-outline-primary:focus {
            background-color: ${color} !important;
            border-color: ${color} !important;
            color: #ffffff !important;
        }

        /* 5. LINK BUTTONS (.btn-link trong Settings & Form) */
        .btn-link,
        button.btn-link,
        a.btn-link,
        .o_setting_box .btn-link {
            --btn-color: ${color} !important;
            --btn-hover-color: ${color} !important;
            --btn-active-color: ${color} !important;
            color: ${color} !important;
        }

        /* 6. BREADCRUMBS (Nhạt hơn màu Theme) */
        .breadcrumb-item a,
        .o_control_panel .breadcrumb a {
            color: ${color} !important;
            opacity: 0.6 !important;
            transition: opacity 0.2s ease-in-out;
        }
        .breadcrumb-item a:hover,
        .o_control_panel .breadcrumb a:hover {
            opacity: 1 !important;
            text-decoration: underline !important;
        }
        .breadcrumb-item.active {
            color: #4a5568 !important;
            opacity: 1 !important;
        }

        /* 7. SMART BUTTONS (Chỉ đổi MÀU ICON) */
        .o_form_view .oe_stat_button .o_button_icon,
        .o_form_view .oe_stat_button i,
        .o_form_view .oe_stat_button .fa {
            color: ${color} !important;
        }

        /* 8. PROGRESS BAR (.bg-primary & .o_progress) */
        .bg-primary,
        .o_progressbar .o_progress .bg-primary,
        .o_progressbar .progress-bar,
        .o_kanban_card .o_progressbar .bg-primary,
        .o_field_progressbar .bg-primary {
            background-color: ${color} !important;
            --bg-opacity: 1 !important;
            --background-color: ${color} !important;
        }

        /* 9. NÚT CHATTER / MAIL MESSAGE (Dùng trực tiếp màu Theme) */
        .o_chatter .btn-primary,
        .o_mail_notification a.btn,
        .o_mail_thread .btn-primary,
        .o_mail_thread a.btn,
        .o_activity_view .btn-primary {
            background-color: ${color} !important;
            border-color: ${color} !important;
            color: #ffffff !important;
        }

        /* 10. CHECKBOX & RADIO */
        .form-check-input:checked {
            background-color: ${color} !important;
            border-color: ${color} !important;
        }
    `;

  // console.log(
  //   `%c[PS Theme Customizer] 🎨 Đã áp dụng màu theme ${color} đồng nhất!`,
  //   "color: #ffffff; background: #28a745; padding: 4px 8px; border-radius: 4px; font-weight: bold;",
  // );
}

patch(WebClient.prototype, {
  setup() {
    super.setup();

    onMounted(async () => {
      // 1. Thử lấy từ company service
      const companyService = this.env.services.company;
      let currentCompany = companyService
        ? companyService.currentCompany
        : null;

      let companyId = currentCompany ? currentCompany.id : null;
      let companyName = currentCompany ? currentCompany.name : "";

      // 2. Fallback: Lấy trực tiếp ID từ Cookie 'cids'
      if (!companyId) {
        const match = document.cookie.match(/cids=([^;]+)/);
        if (match) {
          companyId = parseInt(match[1].split("-")[0].split(",")[0], 10);
        }
      }

      if (companyId) {
        // console.log(
        //   `%c[PS Theme Logger] 🚀 Màn hình đã Mount! Company ID hiện tại: ${companyId}` +
        //     (companyName ? ` (${companyName})` : ""),
        //   "color: #ffffff; background: #28a745; padding: 4px 8px; border-radius: 4px; font-weight: bold;",
        // );

        // 3. Gọi ORM đọc trường theme_primary_color của Company tương ứng
        try {
          const orm = this.env.services.orm;
          if (orm) {
            const res = await orm.searchRead(
              "res.company",
              [["id", "=", companyId]],
              ["theme_primary_color"],
            );

            if (res && res.length > 0 && res[0].theme_primary_color) {
              injectThemeColor(res[0].theme_primary_color);
            }
          }
        } catch (err) {
          console.error(
            "[PS Theme ERROR] Không thể đọc màu từ res.company:",
            err,
          );
        }
      } else {
        console.warn("[PS Theme Logger] ⚠️ Chưa xác định được Company ID!");
      }
    });
  },
});
