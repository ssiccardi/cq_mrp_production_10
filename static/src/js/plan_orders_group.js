odoo.define("cq_mrp_production_10", function(require) {
"use strict";

    var core = require("web.core");
    var Sidebar = require("web.Sidebar");
    var Model = require("web.Model");
    var session = require("web.session");

    Sidebar.include({
        add_items: function(section_code, items) {
            var self = this;
            var _super = this._super;
            var Users = new Model("res.users");
            Users.call("has_group", ["mrp.group_mrp_routings"]).done(function(visible_plan_orders) {
                if (!visible_plan_orders) {
                    var new_items = items;
                    if (section_code === "other") {
                        new_items = [];
                        for (var i = 0; i < items.length; i++) {
                            if (!items[i]["action"] || items[i]["action"]["xml_id"] !== "mrp.production_order_server_action") {
                                new_items.push(items[i]);
                            }
                        }
                    }
                    if (new_items.length > 0) {
                        _super.call(self, section_code, new_items);
                    }
                } else {
                    _super.call(self, section_code, items);
                }
            });

        }
    });
});
