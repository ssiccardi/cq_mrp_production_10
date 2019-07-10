# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, exceptions, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_round
from odoo.addons import decimal_precision as dp

class StockMove(models.Model):
    _inherit = 'stock.move'

    @api.multi
    def action_confirm(self):
        #se nel MO confermo un movimento di un componente con distinta phantom deve chiudersi il pop-up della riga, che risulta vuoto visto che è stato eliminato
        res = super(StockMove, self).action_confirm()
        if any(not move.exists() for move in self) and self._context.get('move_form_from_mo', False):
            res = { 'type': 'ir.actions.client', 'tag': 'reload' }
        return res

    # genero i movimenti dei componenti del kit con la loro regole MTO/MTS specifica
    # prima tutti i componenti avevano la stessa route del kit padre
    def _generate_move_phantom(self, bom_line, quantity):
        move_phantom = super(StockMove, self)._generate_move_phantom(bom_line=bom_line, quantity=quantity)
        if move_phantom:
            try:
                mto_route = self.env['stock.warehouse']._get_mto_route()
            except:
                mto_route = False
            product = move_phantom.product_id
            move_phantom.write({
                'raw_material_production_id':  self.raw_material_production_id.id if self.raw_material_production_id else False,
                'price_unit': product.standard_price,
                'procure_method': 'make_to_stock'
            })
            routes = product.route_ids + product.route_from_categ_ids
            pull = self.env['procurement.rule'].search([('route_id', 'in', [x.id for x in routes]), ('location_src_id', '=', move_phantom.location_id.id),
                                                        ('location_id', '=', move_phantom.location_dest_id.id)], limit=1)
            if pull and (pull.procure_method == 'make_to_order'):
                move_phantom.procure_method = pull.procure_method
            elif not pull: # If there is no make_to_stock rule either
                if mto_route and mto_route.id in [x.id for x in routes]:
                    move_phantom.procure_method = 'make_to_order'
        return move_phantom

    # modifco la funzione in modo da esplodere il kit anche se è componente di un MO
    def action_explode(self):
        """ Explodes pickings """
        # in order to explode a move, we must have a picking_type_id on that move because otherwise the move
        # won't be assigned to a picking and it would be weird to explode a move into several if they aren't
        # all grouped in the same picking.
        if not self.picking_type_id and not self.raw_material_production_id:
            return self
        bom = self.env['mrp.bom'].sudo()._bom_find(product=self.product_id)
        if not bom or bom.type != 'phantom':
            return self
        phantom_moves = self.env['stock.move']
        processed_moves = self.env['stock.move']
        factor = self.product_uom._compute_quantity(self.product_uom_qty, bom.product_uom_id) / bom.product_qty
        boms, lines = bom.sudo().explode(self.product_id, factor, picking_type=bom.picking_type_id)
        for bom_line, line_data in lines:
            phantom_moves += self._generate_move_phantom(bom_line, line_data['qty'])

        for new_move in phantom_moves:
            processed_moves |= new_move.action_explode()
        if not self.split_from and self.procurement_id:
            # Check if procurements have been made to wait for
            moves = self.procurement_id.move_ids
            if len(moves) == 1:
                self.procurement_id.write({'state': 'done'})
        if processed_moves and self.state == 'assigned':
            # Set the state of resulting moves according to 'assigned' as the original move is assigned
            processed_moves.write({'state': 'assigned'})
        # delete the move with original product which is not relevant anymore
        self.sudo().unlink()
        return processed_moves
