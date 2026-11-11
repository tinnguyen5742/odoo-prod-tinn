import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class PSHomeDashboard extends Component {
  static template = "ps_home_layout.HomeDashboard";

  setup() {
    this.menuService = useService("menu");
    this.actionService = useService("action");
    this.state = useState({ apps: [] });

    onWillStart(async () => {
      // Lấy trực tiếp danh sách tất cả Top Apps bằng API chuẩn của Odoo
      const allApps = this.menuService.getApps();

      // Lọc bỏ chính Menu Home hiện tại (nếu có)
      this.state.apps = allApps.filter(
        (app) => app.xmlid !== "ps_home_layout.menu_ps_home_root",
      );
    });
  }

  openApp(app) {
    this.menuService.selectMenu(app);
  }
}

registry.category("actions").add("ps_home_dashboard_action", PSHomeDashboard);
