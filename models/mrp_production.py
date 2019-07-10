# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict
import math

from odoo import api, fields, models, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError


class MrpProduction(models.Model):

    _inherit = 'mrp.production'

    #rende visibile il bottone post inventory anche se non è impostata un metodo di costo sul template
    @api.multi
    @api.depends('move_raw_ids.quantity_done', 'move_raw_ids.state', 'move_finished_ids.quantity_done', 'move_finished_ids.state')
    def _compute_post_visible(self):
        for order in self:
            if order.product_tmpl_id._is_cost_method_standard() or not order.product_tmpl_id.property_cost_method:
                order.post_visible = any((x.quantity_done > 0 and x.state not in ['done', 'cancel']) for x in order.move_raw_ids) or \
                    any((x.quantity_done > 0 and x.state not in ['done','cancel']) for x in order.move_finished_ids)
            else:
                order.post_visible = any((x.quantity_done > 0 and x.state not in ['done','cancel']) for x in order.move_finished_ids)

    #compila i campi mancanti quando viene aggiunta una riga tra le materie prime (vedere la create di mrp_production)
    @api.one
    @api.constrains('move_raw_ids')
    def _check_create_new_move(self):
        if self.routing_id:
            routing = self.routing_id
        else:
            routing = self.bom_id.routing_id
        if routing and routing.location_id:
            source_location = routing.location_id
        else:
            source_location = self.location_src_id
        draft_moves = self.move_raw_ids.filtered(lambda x: x.state == 'draft')
        draft_moves.write({'name': self.name, 
                           'origin': self.name, 
                           'location_id': source_location.id,
                           'location_dest_id': self.product_id.property_stock_production.id,
                           'date': self.date_planned_start,
                           'date_expected': self.date_planned_start,
                           'raw_material_production_id': self.id,
                           'company_id': self.company_id.id,
                           'procure_method': 'make_to_stock',
                           'warehouse_id': source_location.get_warehouse().id,
                           'group_id': self.procurement_group_id.id })
        # eseguo la _adjust_procure_method solo per i nuovi movimenti creati in bozza
        try:
            mto_route = self.env['stock.warehouse']._get_mto_route()
        except:
            mto_route = False
        for move in draft_moves:
            product = move.product_id
            routes = product.route_ids + product.route_from_categ_ids
            pull = self.env['procurement.rule'].search([('route_id', 'in', [x.id for x in routes]), ('location_src_id', '=', move.location_id.id),
                                                        ('location_id', '=', move.location_dest_id.id)], limit=1)
            if pull and (pull.procure_method == 'make_to_order'):
                move.procure_method = pull.procure_method
            elif not pull: # If there is no make_to_stock rule either
                if mto_route and mto_route.id in [x.id for x in routes]:
                    move.procure_method = 'make_to_order'

    @api.multi
    def post_inventory(self):
        #oltre ai movimenti fatti e cancellati ignoro anche quelli in bozza
        for order in self:
            moves_not_to_do = order.move_raw_ids.filtered(lambda x: x.state == 'done')
            moves_to_do = order.move_raw_ids.filtered(lambda x: x.state not in ('done', 'cancel', 'draft'))
            moves_to_do.action_done()
            moves_to_do = order.move_raw_ids.filtered(lambda x: x.state == 'done') - moves_not_to_do
            order._cal_price(moves_to_do)
            moves_to_finish = order.move_finished_ids.filtered(lambda x: x.state not in ('done','cancel','draft'))
            moves_to_finish.action_done()
            
            for move in moves_to_finish:
                #Group quants by lots
                lot_quants = {}
                raw_lot_quants = {}
                quants = self.env['stock.quant']
                if move.has_tracking != 'none':
                    for quant in move.quant_ids:
                        lot_quants.setdefault(quant.lot_id.id, self.env['stock.quant'])
                        raw_lot_quants.setdefault(quant.lot_id.id, self.env['stock.quant'])
                        lot_quants[quant.lot_id.id] |= quant
                for move_raw in moves_to_do:
                    if (move.has_tracking != 'none') and (move_raw.has_tracking != 'none'):
                        for lot in lot_quants:
                            lots = move_raw.move_lot_ids.filtered(lambda x: x.lot_produced_id.id == lot).mapped('lot_id')
                            raw_lot_quants[lot] |= move_raw.quant_ids.filtered(lambda x: (x.lot_id in lots) and (x.qty > 0.0))
                    else:
                        quants |= move_raw.quant_ids.filtered(lambda x: x.qty > 0.0)
                if move.has_tracking != 'none':
                    for lot in lot_quants:
                        lot_quants[lot].sudo().write({'consumed_quant_ids': [(6, 0, [x.id for x in raw_lot_quants[lot] | quants])]})
                else:
                    move.quant_ids.sudo().write({'consumed_quant_ids': [(6, 0, [x.id for x in quants])]})
            order.action_assign()
            #scrivo sui quanti prodotti il loro costo unitario come somma dei costi dei quanti consumati
            for move in moves_to_finish:
                quant_ids = move.quant_ids
                consumed_quants = quant_ids.mapped('consumed_quant_ids')
                if consumed_quants and quant_ids:
                    cost = sum(consumed_quant.qty * consumed_quant.real_unit_cost for consumed_quant in consumed_quants)
                    qty = sum(quant_id.qty for quant_id in quant_ids)
                    price_unit = qty and cost/qty or 0
                    quant_ids.sudo().write({'real_unit_cost': price_unit})
                else:
                    quant_ids.sudo().write({'real_unit_cost': move.product_id.standard_price})
        return True

    @api.multi
    def button_mark_done(self):
        self.ensure_one()
        for wo in self.workorder_ids:
            if wo.time_ids.filtered(lambda x: (not x.date_end) and (x.loss_type in ('productive', 'performance'))):
                raise UserError(_('Work order %s is still running') % wo.name)
        self.post_inventory()
        moves_to_cancel = (self.move_raw_ids | self.move_finished_ids).filtered(lambda x: x.state not in ('done', 'cancel'))
        if not self._context.get('force_button_mark_done') and moves_to_cancel:
            view_id = self.env.ref('cq_mrp_production_10.popup_confim_button_mark_done').id
            return {
                'name': 'Conferma Azione',
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'mrp.production',
                'views': [(view_id, 'form')],
                'view_id': view_id,
                'target': 'new',
                'res_id': self.ids[0],
                'context': self._context}
        moves_to_cancel.action_cancel()
        self.write({'state': 'done', 'date_finished': fields.Datetime.now()})
        self.env["procurement.order"].search([('production_id', 'in', self.ids)]).check()
        return self.write({'state': 'done'})

    #oltre ai movimenti fatti e cancellati ignoro anche quelli in bozza 
    @api.multi
    def do_unreserve(self):
        for production in self:
            production.move_raw_ids.filtered(lambda x: x.state not in ('done', 'cancel', 'draft')).do_unreserve()
        return True

    #oltre ai movimenti fatti e cancellati ignoro anche quelli in bozza 
    @api.multi
    def button_scrap(self):
        self.ensure_one()
        return {
            'name': _('Scrap'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'stock.scrap',
            'view_id': self.env.ref('stock.stock_scrap_form_view2').id,
            'type': 'ir.actions.act_window',
            'context': {'default_production_id': self.id,
                        'product_ids': (self.move_raw_ids.filtered(lambda x: x.state not in ('done', 'cancel', 'draft')) | self.move_finished_ids.filtered(lambda x: x.state == 'done')).mapped('product_id').ids,
                        },
            'target': 'new',
        }
