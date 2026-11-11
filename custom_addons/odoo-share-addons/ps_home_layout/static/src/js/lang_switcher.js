/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";
import { browser } from "@web/core/browser/browser";
import { WebClient } from "@web/webclient/webclient";
import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount } from "@odoo/owl";

patch(WebClient.prototype, {
  setup() {
    super.setup();
    let observer = null;
    let isProcessing = false;

    const injectLangSwitcher = async () => {
      const urlParams = new URLSearchParams(window.location.search);
      const isDebug = urlParams.has("debug");

      // 1. Kiểm tra xem nút đã tồn tại trên Navbar chưa (Dù ở bất kỳ vị trí nào)
      const existingContainer = document.querySelector(
        ".o_ps_lang_switcher_container",
      );

      if (!isDebug) {
        if (existingContainer) existingContainer.remove();
        return;
      }

      // Nếu đã tồn tại rồi thì tuyệt đối không tạo thêm nữa
      if (existingContainer) return;

      // 2. Tìm icon con bọ (Debug dropdown) trên Navbar
      const debugToggle = document
        .querySelector(
          ".o_navbar .o_debug_manager, .o_navbar [title*='Debug'], .o_navbar .fa-bug",
        )
        ?.closest(".dropdown, .o_menu_systray_item, div");

      if (!debugToggle) return;

      // 3. Lấy dữ liệu ngôn ngữ từ Odoo RPC
      let languages = [];
      let currentLang = "en_US";
      try {
        languages = await rpc("/web/dataset/call_kw", {
          model: "res.lang",
          method: "get_installed",
          args: [],
          kwargs: {},
        });

        const userInfo = await rpc("/web/dataset/call_kw", {
          model: "res.users",
          method: "read",
          args: [[user.userId], ["lang"]],
          kwargs: {},
        });
        if (userInfo && userInfo.length > 0) {
          currentLang = userInfo[0].lang || "en_US";
        }
      } catch (e) {
        console.error("Error loading languages:", e);
        return;
      }

      // Kiểm tra lại một lần nữa trước khi render tránh race condition
      if (document.querySelector(".o_ps_lang_switcher_container")) return;

      // 4. Tạo giao diện HTML cho nút chọn ngôn ngữ
      const container = document.createElement("div");
      container.className =
        "o_menu_systray_item dropdown o_ps_lang_switcher_container px-1 d-flex align-items-center";

      const currentCode = currentLang.split("_")[0].toUpperCase();

      container.innerHTML = `
                <a class="dropdown-toggle o-no-caret d-flex align-items-center text-white text-decoration-none px-2 py-1 rounded" 
                   data-bs-toggle="dropdown" 
                   data-bs-display="static" 
                   href="#" 
                   role="button" 
                   title="Quick Language Preferences"
                   style="cursor: pointer; background: rgba(255, 255, 255, 0.1);">
                    <i class="fa fa-language fs-5 me-1"></i>
                    <span class="small fw-bold">${currentCode}</span>
                </a>
                <div class="text-gray-900 dropdown-menu dropdown-menu-end p-3 shadow-lg border-0" style="width: 260px; margin-top: 8px; z-index: 100000;">
                    <div class="mb-3">
                        <select class="form-select form-select-sm o_ps_lang_select" style="color: #000000 !important;">
                            ${languages.map((l) => `<option value="${l[0]}" ${l[0] === currentLang ? "selected" : ""}>${l[1]}</option>`).join("")}
                        </select>
                    </div>
                    <div class="d-flex justify-content-end">
                        <button class="btn btn-danger btn-sm px-3 o_ps_save_lang_btn"
                                style="background-color: #dc3545 !important; border-color: #dc3545 !important; color: #ffffff !important;"
                                onmouseover="this.style.backgroundColor='#dc3545 !important'; this.style.borderColor='#dc3545 !important'; this.style.color='#ffffff !important';"
                                onmouseout="this.style.backgroundColor='#dc3545 !important'; this.style.borderColor='#dc3545 !important'; this.style.color='#ffffff !important';"
                                onfocus="this.style.backgroundColor='#dc3545 !important'; this.style.borderColor='#dc3545 !important'; this.style.color='#ffffff !important';"
                                onactive="this.style.backgroundColor='#dc3545 !important'; this.style.borderColor='#dc3545 !important'; this.style.color='#ffffff !important';">
                            Update Preferences
                        </button>
                    </div>
                </div>
            `;

      // 5. Gắn sự kiện click nút Update Preferences
      const saveBtn = container.querySelector(".o_ps_save_lang_btn");
      const selectTag = container.querySelector(".o_ps_lang_select");

      saveBtn.addEventListener("click", async () => {
        const selectedVal = selectTag.value;
        saveBtn.disabled = true;
        saveBtn.textContent = "Updating...";
        try {
          await rpc("/web/dataset/call_kw", {
            model: "res.users",
            method: "write",
            args: [[user.userId], { lang: selectedVal }],
            kwargs: {},
          });
          browser.location.reload();
        } catch (err) {
          console.error("Failed to update lang:", err);
          saveBtn.disabled = false;
          saveBtn.textContent = "Update Preferences";
        }
      });

      // 6. Chèn vào NGAY KẾ BÊN con bọ
      debugToggle.parentNode.insertBefore(container, debugToggle);
    };

    const safeProcess = () => {
      if (isProcessing) return;
      isProcessing = true;
      if (observer) observer.disconnect();

      try {
        injectLangSwitcher();
      } catch (err) {
        console.error("Lang Switcher JS Error:", err);
      } finally {
        isProcessing = false;
        if (observer) {
          // Chỉ quan sát phần thân navbar thay vì toàn bộ body để giảm tải và tránh trigger vô hạn
          const navbar = document.querySelector(".o_navbar");
          if (navbar) {
            observer.observe(navbar, { childList: true, subtree: true });
          } else {
            observer.observe(document.body, { childList: true, subtree: true });
          }
        }
      }
    };

    onMounted(() => {
      setTimeout(safeProcess, 300);
      observer = new MutationObserver(() => {
        safeProcess();
      });
      const navbar = document.querySelector(".o_navbar");
      observer.observe(navbar || document.body, {
        childList: true,
        subtree: true,
      });
    });

    onWillUnmount(() => {
      if (observer) observer.disconnect();
    });
  },
});
