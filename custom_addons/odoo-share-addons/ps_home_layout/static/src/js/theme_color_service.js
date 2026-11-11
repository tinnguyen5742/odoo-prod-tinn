import { registry } from "@web/core/registry";
import { ormService } from "@web/core/orm_service";

function injectThemeColor(color) {
  if (!color) return;

  let styleTag = document.getElementById("ps_theme_custom_style");
  if (!styleTag) {
    styleTag = document.createElement("style");
    styleTag.id = "ps_theme_custom_style";
    document.head.appendChild(styleTag);
  }

  styleTag.innerHTML = `
        :root, [data-bs-theme="light"], body {
            --o-brand-odoo: ${color} !important;
            --o-brand-primary: ${color} !important;
            --primary: ${color} !important;
            --o-navbar-bg: ${color} !important;
            --NavBar-background-color: ${color} !important;
        }

        .o_main_navbar, header.o_navbar, nav.o_main_navbar {
            background-color: ${color} !important;
        }

        .btn-primary, .btn-check:checked + .btn-outline-primary {
            --btn-bg: ${color} !important;
            --btn-border-color: ${color} !important;
            --btn-hover-bg: ${color} !important;
            --btn-hover-border-color: ${color} !important;
            --btn-active-bg: ${color} !important;
            --btn-active-border-color: ${color} !important;
            background-color: ${color} !important;
            border-color: ${color} !important;
        }

        a, .btn-link { 
            color: ${color} !important; 
        }
    `;
  console.log("[PS Theme DEBUG] Applied theme color successfully:", color);
}

// Đăng ký Service chạy song song cùng hệ thống Odoo
export const psThemeService = {
  dependencies: ["orm", "company"],
  async start(env, { orm, company }) {
    const applyCompanyTheme = async () => {
      try {
        // Lấy ID từ company service hoặc fallback trực tiếp từ cookie/session storage của Odoo
        let companyId = company.currentCompany
          ? company.currentCompany.id
          : null;

        if (!companyId) {
          // Fallback lấy từ cids trên URL hoặc Cookie nếu service chưa sẵn sàng
          const match = document.cookie.match(/cids=([^;]+)/);
          if (match) {
            companyId = parseInt(match[1].split("-")[0], 10);
          }
        }

        console.log("[PS Theme DEBUG] Current Company ID detected:", companyId);

        if (companyId) {
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
        console.error("[PS Theme ERROR] Failed to load theme color:", err);
      }
    };

    // Chạy lần đầu ngay khi service start
    await applyCompanyTheme();

    // Lắng nghe sự kiện chuyển đổi công ty
    if (env.bus) {
      env.bus.addEventListener("COMPANY_CHANGED", applyCompanyTheme);
    }
  },
};

// Khai báo đăng ký Service vào hệ thống Odoo Services
registry.category("services").add("psThemeService", psThemeService);
