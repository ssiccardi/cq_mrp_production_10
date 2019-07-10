# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, registry, _
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, float_compare, float_round

class ProcurementOrder(models.Model):
    _inherit = "procurement.order"
    
    bom_esiste = fields.Boolean('esiste Bom?', default=True)
    
    @api.multi
    def make_mo(self):
        """ Create production orders from procurements """
        res = super(ProcurementOrder, self).make_mo()
        Production = self.env['mrp.production']
        for procurement in self:
            ProductionSudo = Production.sudo().with_context(force_company=procurement.company_id.id)
            bom = procurement._get_matching_bom()
            if bom:
                procurement.bom_esiste = True
            else:
                procurement.bom_esiste = False
        return res

    @api.model
    def run_scheduler(self, use_new_cursor=False, company_id=False):
        ''' Cerca gli approvvigionamenti in eccezione per mancanza di bom con regola manufacture e li esegue '''
        super(ProcurementOrder, self).run_scheduler(use_new_cursor=use_new_cursor, company_id=company_id)
        try:
            if use_new_cursor:
                cr = registry(self._cr.dbname).cursor()
                self = self.with_env(self.env(cr=cr))  # TDE FIXME

            ProcurementSudo = self.env['procurement.order'].sudo()
            domain = [('state', '=', 'exception')] + (company_id and [('company_id', '=', company_id)] or [])
            domain += [('rule_id.action', '=', 'manufacture'), ('bom_esiste','=',False)]
            procurements = ProcurementSudo.search(domain)
            procurements.run(autocommit=use_new_cursor)
            if use_new_cursor:
                self.env.cr.commit()

        finally:
            if use_new_cursor:
                try:
                    self._cr.close()
                except Exception:
                    pass
        return {}
