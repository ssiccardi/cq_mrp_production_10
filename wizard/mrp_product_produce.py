# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime

from odoo import api, fields, models, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError, RedirectWarning
from odoo.tools import float_compare, float_round

class MrpProductProduce(models.TransientModel):
    _inherit = "mrp.product.produce"
    #wizard che compila le righe delle materie prime e dei prodotti finiti in base alla quantità prodotta inserita nel pop-up
    
    # le righe dei componenti che non sono legati a una riga di distinta base danno errore
    # ignoro il fattore di quantità di produzione
    @api.model
    def default_get(self, fields):
        res = super(models.TransientModel, self).default_get(fields)
        if self._context and self._context.get('active_id'):
            production = self.env['mrp.production'].browse(self._context['active_id'])
            #serial_raw = production.move_raw_ids.filtered(lambda x: x.product_id.tracking == 'serial')
            main_product_moves = production.move_finished_ids.filtered(lambda x: x.product_id.id == production.product_id.id)
            serial_finished = (production.product_id.tracking == 'serial')
            serial = bool(serial_finished)
            if serial_finished:
                quantity = 1.0
            else:
                quantity = production.product_qty - sum(main_product_moves.mapped('quantity_done'))
                quantity = quantity if (quantity > 0) else 0
            lines = []
            existing_lines = []
            for move in production.move_raw_ids.filtered(lambda x: (x.product_id.tracking != 'none') and x.state not in ('done', 'cancel', 'draft')):
                if not move.move_lot_ids.filtered(lambda x: not x.lot_produced_id):
                    qty = move.bom_line_id and quantity / move.bom_line_id.bom_id.product_qty * move.bom_line_id.product_qty or move.product_uom_qty
                    if move.product_id.tracking == 'serial':
                        while float_compare(qty, 0.0, precision_rounding=move.product_uom.rounding) > 0:
                            lines.append({
                                'move_id': move.id,
                                'quantity': min(1,qty),
                                'quantity_done': 0.0,
                                'plus_visible': True,
                                'product_id': move.product_id.id,
                                'production_id': production.id,
                            })
                            qty -= 1
                    else:
                        lines.append({
                            'move_id': move.id,
                            'quantity': qty,
                            'quantity_done': 0.0,
                            'plus_visible': True,
                            'product_id': move.product_id.id,
                            'production_id': production.id,
                        })
                else:
                    existing_lines += move.move_lot_ids.filtered(lambda x: not x.lot_produced_id).ids

            res['serial'] = serial
            res['production_id'] = production.id
            res['product_qty'] = quantity
            res['product_id'] = production.product_id.id
            res['product_uom_id'] = production.product_uom_id.id
            res['consume_line_ids'] = map(lambda x: (0,0,x), lines) + map(lambda x:(4, x), existing_lines)
        return res
        
    @api.multi
    def do_produce(self):
        # Nothing to do for lots since values are created using default data (stock.move.lots)
        moves = self.production_id.move_raw_ids
        quantity = self.product_qty
        if float_compare(quantity, 0, precision_rounding=self.product_uom_id.rounding) <= 0:
            raise UserError(_('You should at least produce some quantity'))
        for move in moves.filtered(lambda x: x.product_id.tracking == 'none' and x.state not in ('draft','done', 'cancel')):
            rounding = move.product_uom.rounding
            if move.unit_factor:
                quantity_done_store = move.quantity_done_store + float_round(quantity * move.unit_factor, precision_rounding=rounding)
                if float_compare(quantity_done_store, move.product_uom_qty, precision_rounding=rounding) <= 0:
                    move.quantity_done_store = quantity_done_store
                else:
                    move.quantity_done_store = move.product_uom_qty
            else:
                # i movimenti delle materie prime aggiunti a mano non hanno unit_factor
                # imposto la quantità fatta in proporzione alla quantità da produrre e quella prodotta
                original_quantity = self.production_id.product_qty - self.production_id.qty_produced
                move.quantity_done_store = float_round(quantity * move.product_uom_qty / original_quantity, precision_rounding=rounding)
        moves = self.production_id.move_finished_ids.filtered(lambda x: x.product_id.tracking == 'none' and x.state not in ('done', 'cancel'))
        for move in moves:
            rounding = move.product_uom.rounding
            if move.product_id.id == self.production_id.product_id.id:
                move.quantity_done_store += float_round(quantity, precision_rounding=rounding)
            elif move.unit_factor:
                # byproducts handling
                move.quantity_done_store += float_round(quantity * move.unit_factor, precision_rounding=rounding)
        self.check_finished_move_lots()
        if self.production_id.state == 'confirmed':
            self.production_id.write({
                'state': 'progress',
                'date_start': datetime.now(),
            })
        return {'type': 'ir.actions.act_window_close'}
