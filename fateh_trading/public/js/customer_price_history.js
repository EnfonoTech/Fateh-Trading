frappe.provide("fateh_trading.test");

// Configuration for supported doctypes
const DOCTYPE_CONFIG = {
    "Sales Invoice": {
        child_doctype: "Sales Invoice Item",
        customer_field: "customer"
    },
    "Delivery Note": {
        child_doctype: "Delivery Note Item",
        customer_field: "customer"
    },
    "Sales Order": {
        child_doctype: "Sales Order Item",
        customer_field: "customer"
    },
    "Quotation": {
        child_doctype: "Quotation Item",
        customer_field: "party_name"
    }
};

// Generic function to setup form handlers for a doctype
function setup_doctype_handlers(doctype, config) {
    frappe.ui.form.on(doctype, {
        refresh(frm) {
            // Store config on the form for later access
            if (!frm.__fateh_trading_config) {
                frm.__fateh_trading_config = config;
            }
            
            if (!frm.__price_assist_row_bound) {
                frm.fields_dict.items.grid.wrapper.on("click", ".grid-row", function () {
                    const row_name = $(this).attr("data-name");
                    if (!row_name) return;

                    const row = locals[config.child_doctype]?.[row_name];
                    if (!row) return;

                    if (frm.__price_assist_row && frm.__price_assist_row !== row) {
                        fateh_trading.test.hide(frm.__price_assist_row);
                    }

                    frm.__price_assist_row = row;
                });
                frm.__price_assist_row_bound = true;
            }

            if (frm.__price_assist_btn_added) return;

            const btn = frm.fields_dict.items.grid.add_custom_button(__("Price Assist"), () => {
                const row = frm.__price_assist_row;
                const config = frm.__fateh_trading_config || { customer_field: "customer" };

                if (!row) {
                    frappe.msgprint("Please click an Item row first");
                    return;
                }

                const customer = frm.doc[config.customer_field];
                if (!customer || !row.item_code) {
                    frappe.msgprint("Customer and Item Code are required");
                    return;
                }

                fateh_trading.test.show(frm, row, config);
            });

            frm.__price_assist_btn_added = true;

            setTimeout(() => {
                const $toolbar = frm.fields_dict.items.grid.wrapper.find(".grid-buttons");
                const $add_multiple = $toolbar.find("button:contains('Add Multiple')").last();
                if ($add_multiple.length && btn) {
                    $(btn).insertAfter($add_multiple);
                }
                
                // Add Price History button after Price Assist button
                add_price_history_button(frm, $toolbar, btn);
            }, 0);
        }
    });

    // Setup child doctype handlers
    const childHandlers = {
        rate(frm, cdt, cdn) {
            fateh_trading.test.updateHighlight(locals[cdt][cdn]);
        }
    };
    
    // Add remove event handler if it exists
    // The event name format is typically: {child_doctype_lowercase}_remove
    const removeEventName = config.child_doctype.toLowerCase().replace(/\s+/g, '_') + '_remove';
    childHandlers[removeEventName] = function(frm, cdt, cdn) {
        fateh_trading.test.hide(locals[cdt]?.[cdn]);
    };
    
    frappe.ui.form.on(config.child_doctype, childHandlers);
    
    // Also listen to items_remove on parent form as fallback
    frappe.ui.form.on(doctype, {
        items_remove(frm) {
            // Clear any open price assist popups when items are removed
            if (frm.__price_assist_row) {
                fateh_trading.test.hide(frm.__price_assist_row);
                frm.__price_assist_row = null;
            }
        }
    });
}

// Setup handlers for all supported doctypes
for (const [doctype, config] of Object.entries(DOCTYPE_CONFIG)) {
    setup_doctype_handlers(doctype, config);
}

$.extend(fateh_trading.test, {
    show(frm, row, config) {
        this.hide(row);
        
        // Get customer field name from config (defaults to 'customer' if not specified)
        const customerField = config?.customer_field || "customer";
        const customer = frm.doc[customerField];
        
        frappe.call({
            method: "fateh_trading.test.get_item_insights",
            args: {
                customer: customer,
                item_code: row.item_code,
                company: frm.doc.company,
                limit: 6,
                other_limit: 5
            },
            callback: r => {
                this.render(frm, row, r.message || {}, config);
            }
        });
    },

    render(frm, row, insights, config) {
        this.hide(row);

        const price_history = insights.price_history || [];
        const other_customers = insights.other_customers || [];
        const stock = insights.stock || [];

        const avg_rate = flt(insights.avg_rate || 0);
        const last_rate = flt(insights.last_rate || 0);

        const id = `si-price-assist-${row.name}`;
        const $box = $(`<div class="si-price-assist" id="${id}"></div>`).appendTo("body");

        // Get customer field name from config (defaults to 'customer' if not specified)
        const customerField = config?.customer_field || "customer";
        const customer = frm.doc[customerField];

        $box.append(`<div class="pa-customer">${customer}</div>`);
        $box.append(`<div class="pa-title">Price History: ${row.item_name || row.item_code}</div>`);

        const current_rate = flt(row.rate);
        let diff_text = "", diff_class = "";

        if (current_rate && last_rate) {
            const diff_pct = ((current_rate - last_rate) / last_rate) * 100;
            const abs = Math.abs(diff_pct);
            diff_class = abs <= 5 ? "pa-price-good" : abs <= 20 ? "pa-price-warn" : "pa-price-bad";
            diff_text = `${diff_pct >= 0 ? "+" : ""}${diff_pct.toFixed(1)}% vs last price`;
        }

        $box.append(`
            <div class="pa-summary ${diff_class}">
                <div class="pa-summary-main">
                    <div><label>Last</label><span>${last_rate || "-"}</span></div>
                    <div><label>Average</label><span>${avg_rate ? avg_rate.toFixed(2) : "-"}</span></div>
                    <div><label>Current</label><span>${current_rate || "-"}</span></div>
                </div>
                <div class="pa-summary-warning">${diff_text}</div>
            </div>
        `);

        price_history.forEach(d => {
            $box.append($(`
                <div class="pa-line">
                    <div class="pa-left">
                        <b>${d.rate}</b> (${d.currency}, ${d.uom})
                        <small>${d.qty} qty • ${frappe.format(d.posting_date, "Date")}</small>
                        <small class="pa-inv">
                            <a href="/app/sales-invoice/${encodeURIComponent(d.si)}" target="_blank">${d.si}</a>
                        </small>
                    </div>
                    <button class="pa-use">Use</button>
                </div>
            `).data("rate", d.rate));
        });

        if (other_customers.length) {
            $box.append(`<div class="pa-section-title">Other customers paying</div>`);
            other_customers.forEach(d => {
                $box.append($(`
                    <div class="pa-line pa-other">
                        <div class="pa-left">
                            <b>${d.rate}</b> (${d.currency}, ${d.uom})
                            <small>${d.customer}</small>
                        </div>
                        <button class="pa-use">Use</button>
                    </div>
                `).data("rate", d.rate));
            });
        }

        if (stock.length) {
            $box.append(`<div class="pa-section-title">Stock by Warehouse</div>`);
            const maxQty = Math.max(...stock.map(s => flt(s.projected_qty))) || 1;

            stock.forEach(s => {
                const fill = Math.min(100, (flt(s.projected_qty) / maxQty) * 100);
                $box.append(`
                    <div class="ps-line">
                        <div class="ps-left">
                            <b>${s.warehouse}</b>
                            <small>${s.projected_qty} available</small>
                        </div>
                        <div class="ps-bar-wrap">
                            <div class="ps-bar" style="width:${fill}%"></div>
                        </div>
                        <button class="ps-use">Use</button>
                    </div>
                `);
            });
        }

        const $input = $(`.grid-row[data-name="${row.name}"] input[data-fieldname="item_code"]`);
        if ($input.length) {
            const pos = $input.offset();
            $box.css({ top: pos.top + $input.outerHeight() + 8, left: pos.left });
        }

        $box.on("click", ".pa-use", function () {
            frappe.model.set_value(row.doctype, row.name, "rate", $(this).closest(".pa-line").data("rate"));
            frappe.model.set_value(row.doctype, row.name, "actual_rate", $(this).closest(".pa-line").data("rate"));
            fateh_trading.test.hide(row);
        });

        $box.on("click", ".ps-use", function () {
            frappe.model.set_value(row.doctype, row.name, "warehouse", $(this).closest(".ps-line").find("b").text());
        });

        row._price_id = id;
    },

    updateHighlight(row) {
        if (!row || !row._price_id) return;
        const rate = flt(row.rate);
        $(`#${row._price_id} .pa-line`).each(function () {
            $(this).toggleClass("pa-match", flt($(this).data("rate")) === rate);
        });
    },

    hide(row) {
        if (row?._price_id) {
            $(`#${row._price_id}`).remove();
            delete row._price_id;
        }
    }
});

$(document).on("click.price_assist", function (e) {
    if ($(e.target).closest(".si-price-assist").length) return;
    if ($(e.target).closest(".grid-row").length) return;

    const frm = cur_frm;
    if (frm?.__price_assist_row) {
        fateh_trading.test.hide(frm.__price_assist_row);
    }
});

// Price History Button Functions
function add_price_history_button(frm, $toolbar, price_assist_btn) {
    if (frm.price_history_btn_added) return;
    
    // Check if button already exists
    if ($toolbar.find("button:contains('Show Price History')").length > 0) {
        frm.price_history_btn_added = true;
        return;
    }

    // Find the Price Assist button (which was just positioned)
    let $target = price_assist_btn ? $(price_assist_btn) : $toolbar.find("button:contains('Price Assist')").last();
    
    // If Price Assist not found, try Add Multiple button
    if ($target.length === 0) {
        $target = $toolbar.find("button:contains('Add Multiple')").last();
    }

    // Create the button
    let price_history_btn = $(`<button type="button" class="btn btn-secondary btn-xs btn-custom" style="margin-left: 10px;">
      ${__('Show Price History')}
    </button>`);

    price_history_btn.on('click', function () {
      open_item_history_dialog(frm);
    });

    // Insert after target button
    if ($target.length > 0) {
        price_history_btn.insertAfter($target);
    } else {
        $toolbar.append(price_history_btn);
    }
    
    frm.price_history_btn_added = true;
}

function open_item_history_dialog(frm, default_item_code) {
    // Always create a fresh dialog
    let d = new frappe.ui.Dialog({
      title: 'Item Sales & Purchase Price History',
      fields: [
        { fieldname: 'item_code', label: 'Item Code', fieldtype: 'Link', options: 'Item', default: default_item_code },
        { fieldname: 'item_description', label: 'Item Description', fieldtype: 'Small Text', read_only: 1 },
        { fieldname: 'results', fieldtype: 'HTML' }
        ],

      size: 'extra-large',
      primary_action_label: 'Close',
      primary_action: function () {
        d.hide();
      }
    });
  
    d.show();
    
  
    setTimeout(() => {
      // Bind using Frappe's built-in onchange for the Link field
      if (d.fields_dict.item_code) {
        d.fields_dict.item_code.df.onchange = function () {
          const item_code = d.get_value('item_code');
          if (item_code) {

            frappe.db.get_value('Item', item_code, 'description', r => {
              d.set_value('item_description', r?.description || '');
            });

            fetch_item_history(item_code, 20, d);
          }
        };
      }
  
      // Auto-fetch if dialog opened with default item
      if (default_item_code) {

        frappe.db.get_value('Item', default_item_code, 'description', r => {
          d.set_value('item_description', r?.description || '');
        });

        fetch_item_history(default_item_code, 20, d);
      }
    }, 200);
  }
  
  function fetch_item_history(item_code, limit, dialog) {
    dialog.fields_dict.results.$wrapper.html('<div class="text-muted">Loading…</div>');
  
    frappe.call({
      method: 'fateh_trading.api.get_item_sales_history',
      args: { item_code, limit },
      callback: function (r) {
        const rows = r.message || [];
        if (!rows.length) {
          dialog.fields_dict.results.$wrapper.html('<div class="text-muted">No history found.</div>');
          return;
        }
  
        dialog.fields_dict.results.$wrapper.html(render_history_table(rows));

        // enable invoice links
        dialog.fields_dict.results.$wrapper.find('[data-doctype][data-name]').on('click', function () {
          frappe.set_route('Form', this.getAttribute('data-doctype'), this.getAttribute('data-name'));
        });

        // re-init filters each time with proper timing and scope
        setTimeout(() => {
          setupTableFilters(dialog);
        }, 100);
      },
      error: function (err) {
        dialog.fields_dict.results.$wrapper.html('<div class="text-danger">Error fetching data: ' + err.message + '</div>');
      }
    });
  }
  
  function render_history_table(rows) {
    // Check if last_purchase_rate exists in rows
    const show_purchase_rate = rows.length && "last_purchase_rate" in rows[0];
    let out = '';

    // Table start
    out += '<div class="mt-3"><table class="table table-bordered table-sm" id="price-history-table">';
    out += '<thead><tr>';
    out += '<th>Item Code</th><th>Item Name</th><th>Customer</th><th>Sales Rate (Txn)</th><th>Qty</th>';
    if (show_purchase_rate) out += '<th>Last Purchase Rate</th>';
    out += '</tr></thead>';
   
    out += '<tbody>';
    rows.forEach(function(r) {
        out += '<tr>';
        out += `<td>${frappe.utils.escape_html(r.item_code || '')}</td>`;
        out += `<td>${frappe.utils.escape_html(r.item_name || '')}</td>`;
        out += `<td>${frappe.utils.escape_html(r.customer || '')}</td>`;
        out += `<td>${format_currency(r.sales_rate || 0, r.currency || '')}</td>`;
        out += `<td>${format_number(r.qty || 0)}</td>`;
        if (show_purchase_rate) {
            out += `<td>${format_currency(r.last_purchase_rate || 0, r.currency || '')}</td>`;
        }
        out += '</tr>';
    });
    out += '</tbody></table></div>';

    return out; 
}

  function setupTableFilters(dialog) {
    // Use dialog wrapper to scope the search
    const table = dialog.fields_dict.results.$wrapper.find('#price-history-table')[0];
    if (!table) return;

    const filterInputs = table.querySelectorAll('.filter-row input');
    const tbody = table.querySelector('tbody');
    if (!tbody || !filterInputs.length) return;

    // remove old handlers
    filterInputs.forEach(input => {
      if (input._filterHandler) {
        input.removeEventListener('input', input._filterHandler);
        delete input._filterHandler;
      }
    });

    // attach new ones
    filterInputs.forEach((input, index) => {
      input._filterHandler = function () {
        applyAllFilters(dialog);
      };
      input.addEventListener('input', input._filterHandler);
    });
  }
  
  function applyAllFilters(dialog) {
    // Use dialog wrapper to scope the search
    const table = dialog.fields_dict.results.$wrapper.find('#price-history-table')[0];
    if (!table) return;

    const rows = table.querySelectorAll('tbody tr');
    const filterInputs = table.querySelectorAll('.filter-row input');

    rows.forEach(row => {
      let shouldShow = true;

      filterInputs.forEach((input, j) => {
        const val = input.value.toLowerCase().trim();
        if (!val) return;

        const cell = row.cells[j];
        if (cell) {
          const cellText = (cell.textContent || '').toLowerCase();
          if (cellText.indexOf(val) === -1) {
            shouldShow = false;
          }
        }
      });

      row.style.display = shouldShow ? '' : 'none';
    });
  }


$(`<style>
.si-price-assist{position:absolute;z-index:1050;width:340px;background:#0d1117;color:#fff;padding:14px;border-radius:12px;box-shadow:0 8px 25px rgba(0,0,0,.45);font-size:13px}
.pa-customer{font-size:12px;color:#c9d1d9;margin-bottom:4px;opacity:.85}
.pa-title{font-weight:600;font-size:14px;margin-bottom:10px;opacity:.9}
.pa-summary{border-radius:10px;padding:10px;margin-bottom:10px;background:#111b24;border:1px solid rgba(255,255,255,.06)}
.pa-summary-main{display:flex;justify-content:space-between;gap:6px}
.pa-summary-main label{display:block;font-size:10px;text-transform:uppercase;opacity:.6}
.pa-summary-main span{font-size:13px;font-weight:600}
.pa-summary-warning{margin-top:6px;font-size:11px}
.pa-price-good{border-color:rgba(0,200,120,.4)}
.pa-price-good .pa-summary-warning{color:#00e676}
.pa-price-warn{border-color:rgba(255,200,0,.4)}
.pa-price-warn .pa-summary-warning{color:#ffeb3b}
.pa-price-bad{border-color:rgba(255,80,80,.5)}
.pa-price-bad .pa-summary-warning{color:#ff5252}
.pa-section-title{font-size:11px;text-transform:uppercase;opacity:.7;margin:6px 0 4px}
.pa-line{padding:10px;margin-bottom:8px;background:#111b24;border-radius:10px;display:flex;justify-content:space-between;align-items:center;border:1px solid rgba(255,255,255,.05)}
.pa-line:hover{background:#16212c}
.pa-line.pa-other{opacity:.85}
.pa-left b{font-size:14px;font-weight:600}
.pa-left small{display:block;font-size:10px;opacity:.75}
.pa-use{padding:6px 14px;font-size:11px;border-radius:8px;border:none;background:linear-gradient(90deg,#00d2ff,#3a7bd5);color:#fff;font-weight:600;cursor:pointer}
.ps-line{padding:8px;margin-bottom:6px;background:#101820;border-radius:10px;display:flex;align-items:center;gap:8px;border:1px solid rgba(255,255,255,.06)}
.ps-left{min-width:120px}
.ps-left small{font-size:10px;opacity:.75}
.ps-bar-wrap{flex:1;height:6px;background:rgba(255,255,255,.06);border-radius:999px;overflow:hidden}
.ps-bar{height:6px;border-radius:999px;background:linear-gradient(90deg,#00e676,#00b0ff)}
.ps-use{padding:4px 10px;font-size:10px;border-radius:999px;border:none;background:#263238;color:#e0f7fa;cursor:pointer}
</style>`).appendTo("head");

