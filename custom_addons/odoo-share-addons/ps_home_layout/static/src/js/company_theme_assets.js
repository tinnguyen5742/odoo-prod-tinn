import { WebClient } from "@web/webclient/webclient";
import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";

function getContrastTextColor(hexColor) {
  if (!hexColor) return "#ffffff";
  let cleanHex = hexColor.replace("#", "");
  if (cleanHex.length === 3) {
    cleanHex = cleanHex
      .split("")
      .map((c) => c + c)
      .join("");
  }
  const r = parseInt(cleanHex.substr(0, 2), 16) || 0;
  const g = parseInt(cleanHex.substr(2, 2), 16) || 0;
  const b = parseInt(cleanHex.substr(4, 2), 16) || 0;

  const yiq = (r * 299 + g * 587 + b * 114) / 1000;
  return yiq >= 150;
}

function injectThemeColor(color) {
  if (!color) return;

  const isLight = getContrastTextColor(color);
  const odooDefaultColor = "#66588E";
  const activeColor = isLight ? odooDefaultColor : color;
  const navTextColor = isLight ? "#212529" : "#ffffff";

  let styleTag = document.getElementById("ps_theme_custom_style");
  if (!styleTag) {
    styleTag = document.createElement("style");
    styleTag.id = "ps_theme_custom_style";
    document.head.appendChild(styleTag);
  }

  styleTag.innerHTML = `
        /* 1. ROOT & GENERAL VARIABLES (CHỈ ÁP DỤNG TRONG ADMIN) */
        body.o_web_client, body.o_web_client [data-bs-theme="light"] {
            --o-brand-odoo: ${color} !important;
            --o-brand-primary: ${color} !important;
            --primary: ${color} !important;
            --o-color-1: ${color} !important;
            --o-navbar-bg: ${color} !important;
            --NavBar-background-color: ${color} !important;
            --bs-primary: ${color} !important;
            --bs-primary-rgb: ${color} !important;
            --link-color: ${activeColor} !important;
            --link-hover-color: ${activeColor} !important;
        }

        /* 2. NAVBAR TOP & XÓA BORDER TỐI DƯỚI NAVBAR TRONG ADMIN */
        body.o_web_client .o_main_navbar, 
        body.o_web_client header.o_navbar, 
        body.o_web_client nav.o_main_navbar {
            background-color: ${color} !important;
            color: ${navTextColor} !important;
            border-bottom: none !important;
            box-shadow: 0 0 0 30px rgba(0, 0, 0, 0.1) !important;
            --Navbar-entry-color: ${navTextColor} !important;
            --o-navbar-entry-color: ${navTextColor} !important;
        }

        body.o_web_client .o_main_navbar *,
        body.o_web_client .o_main_navbar .o_menu_brand,
        body.o_web_client .o_main_navbar .o_menu_sections,
        body.o_web_client .o_main_navbar .o_menu_sections > a,
        body.o_web_client .o_main_navbar .o_menu_sections .dropdown-toggle,
        body.o_web_client .o_main_navbar .o_nav_entry,
        body.o_web_client .o_main_navbar .o_navbar_apps_menu,
        body.o_web_client .o_main_navbar .o_user_menu .dropdown-toggle,
        body.o_web_client .o_main_navbar .oe_topbar_name,
        body.o_web_client .o_main_navbar button,
        body.o_web_client .o_main_navbar span,
        body.o_web_client .o_main_navbar i,
        body.o_web_client .o_main_navbar .fa {
            color: ${navTextColor} !important;
        }

        body.o_web_client .o_main_navbar .o_menu_sections > a:hover,
        body.o_web_client .o_main_navbar .o_menu_sections .show > a,
        body.o_web_client .o_main_navbar button:hover {
            background-color: rgba(0, 0, 0, 0.08) !important;
            color: ${navTextColor} !important;
        }

        /* 3. BUTTON PRIMARY TRONG ADMIN */
        body.o_web_client .btn-primary {
            background-color: ${color} !important;
            border-color: ${color} !important;
            color: ${isLight ? "#212529" : "#ffffff"} !important;
        }
        body.o_web_client .btn-primary:hover, 
        body.o_web_client .btn-primary:focus, 
        body.o_web_client .btn-primary:active {
            background-color: ${color} !important;
            border-color: ${color} !important;
            filter: brightness(95%);
        }

        /* 4. BUTTON OUTLINE TRONG ADMIN */
        body.o_web_client .btn-outline-primary,
        body.o_web_client .btn-secondary.o_control_panel_main_buttons,
        body.o_web_client .o_control_panel .btn-outline-primary,
        body.o_web_client .o_form_button_create {
            color: ${activeColor} !important;
            border-color: ${activeColor} !important;
            background-color: transparent !important;
        }
        body.o_web_client .btn-outline-primary:hover,
        body.o_web_client .btn-outline-primary:active,
        body.o_web_client .btn-outline-primary:focus {
            background-color: ${activeColor} !important;
            border-color: ${activeColor} !important;
            color: #ffffff !important;
        }

        /* 5. LINK BUTTONS TRONG ADMIN */
        body.o_web_client .btn-link,
        body.o_web_client button.btn-link,
        body.o_web_client a.btn-link,
        body.o_web_client .o_setting_box .btn-link {
            --btn-color: ${activeColor} !important;
            --btn-hover-color: ${activeColor} !important;
            --btn-active-color: ${activeColor} !important;
            color: ${activeColor} !important;
        }

        /* 6. BREADCRUMBS TRONG ADMIN */
        body.o_web_client .breadcrumb-item a,
        body.o_web_client .o_control_panel .breadcrumb a {
            color: ${activeColor} !important;
            opacity: 0.8 !important;
            transition: opacity 0.2s ease-in-out;
        }
        body.o_web_client .breadcrumb-item a:hover,
        body.o_web_client .o_control_panel .breadcrumb a:hover {
            opacity: 1 !important;
            text-decoration: underline !important;
        }
        body.o_web_client .breadcrumb-item.active {
            color: #4a5568 !important;
            opacity: 1 !important;
        }

        /* 7. SMART BUTTONS TRONG ADMIN */
        body.o_web_client .o_form_view .oe_stat_button .o_button_icon,
        body.o_web_client .o_form_view .oe_stat_button i,
        body.o_web_client .o_form_view .oe_stat_button .fa {
            color: ${activeColor} !important;
        }

        /* 8. PROGRESS BAR TRONG ADMIN */
        body.o_web_client .bg-primary,
        body.o_web_client .o_progressbar .o_progress .bg-primary,
        body.o_web_client .o_progressbar .progress-bar,
        body.o_web_client .o_kanban_card .o_progressbar .bg-primary,
        body.o_web_client .o_field_progressbar .bg-primary {
            background-color: ${activeColor} !important;
            --bg-opacity: 1 !important;
            --background-color: ${activeColor} !important;
        }

        /* 9. NÚT CHATTER / MAIL MESSAGE TRONG ADMIN */
        body.o_web_client .o_chatter .btn-primary,
        body.o_web_client .o_mail_notification a.btn,
        body.o_web_client .o_mail_thread .btn-primary,
        body.o_web_client .o_mail_thread a.btn,
        body.o_web_client .o_activity_view .btn-primary {
            background-color: ${color} !important;
            border-color: ${color} !important;
            color: ${isLight ? "#212529" : "#ffffff"} !important;
        }

        /* 10. CHECKBOX & RADIO TRONG ADMIN */
        body.o_web_client .form-check-input:checked {
            background-color: ${activeColor} !important;
            border-color: ${activeColor} !important;
        }

        /* 11. KHẮC PHỤC HOVER / ACTIVE MENU APPS KHI THEME SÁNG TRONG ADMIN */
        .o-overlay-container .o_popover.o_ps_apps_sidebar_popover a[role="menuitem"][aria-selected="true"],
         .o-overlay-container .o_popover.o_ps_apps_sidebar_popover a[role="menuitem"].active,
          .o-overlay-container .o_popover.o_ps_apps_sidebar_popover .o-dropdown-item[aria-selected="true"],
           .o-overlay-container .o_popover.o_ps_apps_sidebar_popover .o-dropdown-item.active
         {
            background-color: ${isLight ? "rgba(0, 0, 0, 0.06)" : "color-mix(in srgb, var(--o-brand-primary, --primary) 15%, transparent)"} !important;
            color: ${isLight ? "#111827" : "var(--primary))"} !important;
            border-left-color: ${activeColor} !important;
        }
    `;
}

patch(WebClient.prototype, {
  setup() {
    super.setup();

    onMounted(async () => {
      const companyService = this.env.services.company;
      let currentCompany = companyService
        ? companyService.currentCompany
        : null;
      let companyId = currentCompany ? currentCompany.id : null;

      if (!companyId) {
        const match = document.cookie.match(/cids=([^;]+)/);
        if (match) {
          companyId = parseInt(match[1].split("-")[0].split(",")[0], 10);
        }
      }

      if (companyId) {
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
      }
    });
  },
});
