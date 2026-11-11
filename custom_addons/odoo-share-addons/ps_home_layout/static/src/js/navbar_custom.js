import { WebClient } from "@web/webclient/webclient";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { onMounted, onWillUnmount } from "@odoo/owl";

patch(WebClient.prototype, {
  setup() {
    super.setup();
    const menuService = useService("menu");
    let observer = null;
    let isProcessing = false;

    // 🎯 1. Bơm Icon VÀ định danh Popover của Apps Menu
    const injectIconsToOverlay = () => {
      const apps = menuService.getApps();
      if (!apps || !apps.length) return;

      // Tìm tất cả các popover đang xuất hiện trên giao diện
      const popovers = document.querySelectorAll(
        ".o-overlay-container .o_popover",
      );

      popovers.forEach((popover) => {
        // Kiểm tra xem popover này có chứa danh sách Apps chính hay không
        // (Dựa vào việc nó chứa các thẻ 'a' có data-section ứng với danh sách app)
        const isAppsMenu = Array.from(
          popover.querySelectorAll("a[role='menuitem']"),
        ).some((a) => {
          const sectionId = a.getAttribute("data-section");
          return apps.some((app) => String(app.id) === sectionId);
        });

        if (isAppsMenu) {
          // 🌟 Gắn class định danh riêng biệt cho popover Apps Menu
          popover.classList.add("o_ps_apps_sidebar_popover");

          // Map icon ứng với từng app
          const iconMap = new Map();
          apps.forEach((app) => {
            const iconSrc =
              app.webIconData ||
              (app.webIcon ? `/${app.webIcon.replace(",", "/")}` : null);
            if (iconSrc) {
              iconMap.set(String(app.id), iconSrc);
              if (app.xmlid) iconMap.set(app.xmlid, iconSrc);
            }
          });

          // Bơm icon vào các item app trong sidebar
          const items = popover.querySelectorAll("a[role='menuitem']");
          items.forEach((a) => {
            if (a.querySelector(".o_ps_custom_icon")) return;

            const sectionId = a.getAttribute("data-section");
            const xmlId = a.getAttribute("data-menu-xmlid");
            const iconSrc = iconMap.get(sectionId) || iconMap.get(xmlId);

            if (iconSrc) {
              const img = document.createElement("img");
              img.src = iconSrc;
              img.className = "o_ps_custom_icon";
              img.style.cssText =
                "width: 24px; height: 24px; margin-right: 12px; object-fit: contain; flex-shrink: 0;";
              img.onerror = () => {
                img.style.display = "none";
              };
              a.insertBefore(img, a.firstChild);
            }
          });
        }
      });
    };

    // 🎯 2. Bơm Icon App Active vào Navbar
    const updateNavbarBrandIcon = () => {
      const currentApp = menuService.getCurrentApp();
      const brandBtn = document.querySelector(
        ".o_navbar .o_menu_brand, .o_navbar .o_menu_sections, .o_navbar [role='menu']",
      );
      const gridBtn = document.querySelector(
        ".o_navbar .o-dropdown-toggle, .o_navbar [data-hotkey='h'], .o_navbar .o_apps_menu",
      );

      if (!currentApp) return;

      const iconSrc =
        currentApp.webIconData ||
        (currentApp.webIcon
          ? `/${currentApp.webIcon.replace(",", "/")}`
          : null);
      if (!iconSrc) return;

      const existingIcon = document.querySelector(".o_ps_navbar_brand_icon");

      if (
        existingIcon &&
        existingIcon.getAttribute("data-app-id") === String(currentApp.id)
      ) {
        return;
      }

      if (existingIcon) {
        existingIcon.remove();
      }

      const img = document.createElement("img");
      img.src = iconSrc;
      img.className = "o_ps_navbar_brand_icon";
      img.setAttribute("data-app-id", String(currentApp.id));
      img.style.cssText =
        "width: 22px; height: 22px; margin-left: 10px; margin-right: 6px; object-fit: contain; vertical-align: middle; display: inline-block;";
      img.onerror = () => {
        img.style.display = "none";
      };

      if (brandBtn) {
        const textNode = Array.from(brandBtn.childNodes).find(
          (node) =>
            node.nodeType === Node.TEXT_NODE &&
            node.textContent.trim().length > 0,
        );
        if (textNode) {
          brandBtn.insertBefore(img, textNode);
          return;
        } else {
          brandBtn.insertBefore(img, brandBtn.firstChild);
          return;
        }
      }

      if (gridBtn && gridBtn.parentNode) {
        if (gridBtn.nextSibling) {
          gridBtn.parentNode.insertBefore(img, gridBtn.nextSibling);
        } else {
          gridBtn.parentNode.appendChild(img);
        }
      }
    };

    const safeProcess = () => {
      if (isProcessing) return;
      isProcessing = true;

      if (observer) observer.disconnect();

      try {
        injectIconsToOverlay();
        updateNavbarBrandIcon();
      } catch (err) {
        console.error("Custom Navbar Error:", err);
      } finally {
        isProcessing = false;
        if (observer) {
          observer.observe(document.body, { childList: true, subtree: true });
        }
      }
    };

    onMounted(() => {
      setTimeout(safeProcess, 200);

      observer = new MutationObserver(() => {
        safeProcess();
      });

      observer.observe(document.body, { childList: true, subtree: true });
    });

    onWillUnmount(() => {
      if (observer) observer.disconnect();
    });
  },
});
