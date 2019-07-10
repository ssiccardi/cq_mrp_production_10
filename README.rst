==============================
MRP enhancements for Odoo r.10
==============================

-------------------------------------------------------------------------------
ATTENZIONE!! All'installazione aggiungere il crea e modifica ai seguenti campi:
-------------------------------------------------------------------------------
* 'lot_id' del modello Record Production (mrp.product.produce)
* 'lot_id' del modello Quantities to Process by lots (stock.move.lots)

Per aggiungerlo Andare in Configurazione --> Struttura Database --> Campi, cercare i campi e flaggare "Mostra crea e modifica"

------------
Funzionalità
------------
* Finchè l'ordine di produzione è in stato confermato è possibile aggiungere e eliminare i prodotti necessari per la produzione. È possibile aggiungere anche una distinta kit.
* Consente il consumo parziale delle materie prime e la produzione parziale di prodotti finiti durante la produzione.
* Modifica allo scheduler: cerca di eseguire nuovamente gli approvvigionamenti in eccezione per mancanza di BoM e, nel caso questa fosse presente, viene creato l'MO. È quindi possibile confermare un ordine di vendita con un prodotto da produrre e inserire la sua BoM in un secondo momento.
* Le route MTS o MTO di prodotti che fanno parte di un kit non vengono ereditate dal prodotto kit padre, ma ogni componente procede con la sua specifica route.
