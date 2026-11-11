/** @odoo-module **/

import {registry} from "@web/core/registry";
import {Component, onMounted} from "@odoo/owl";

class AIChatButton extends Component {
    static template = "ps_elearning.AIChatButton";

    openModal() {
        let modal = document.getElementById("ai_chat_modal");
        if (!modal) {
            modal = document.createElement("div");
            modal.id = "ai_chat_modal";
            modal.style.cssText = `
                position: fixed;
                top: 0; left: 0;
                width: 100%; height: 100%;
                background: rgba(0,0,0,0.5);
                z-index: 9999;
                display: flex;
                align-items: center;
                justify-content: center;
            `;
            modal.innerHTML = `
                <div style="background:white;border-radius:12px;width:90%;height:90%;display:flex;flex-direction:column;overflow:hidden;">
                    <div style="padding:16px 20px;border-bottom:1px solid #dee2e6;display:flex;justify-content:space-between;align-items:center;">
                        <h5 style="margin:0;">💬 AI PatSoft</h5>
                        <button id="close_ai_chat" style="border:none;background:none;font-size:24px;cursor:pointer;">&times;</button>
                    </div>
                    <iframe src="http://42.1.111.50:8061/" style="flex:1;border:none;" allow="microphone"></iframe>
                </div>
            `;
            modal.addEventListener("click", (e) => {
                if (e.target === modal) modal.remove();
            });
            document.body.appendChild(modal);
            document.getElementById("close_ai_chat").addEventListener("click", () => {
                modal.remove();
            });
        } else {
            modal.style.display = "flex";
        }
    }
}

registry.category("view_widgets").add("ai_chat_button", {
    component: AIChatButton,
});