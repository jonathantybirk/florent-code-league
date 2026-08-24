# jonbot_income@5f35893

Mining-movement refinement of the currently selected expected-Elo lineage,
`brynhildr@229b821` (submission v107). This is separate from the v109-based
`jonbot_econ` experiment so ladderfarm can compare both lineages online.

The Core's build timing, economy authorization, builder count, role assignment,
combat, and defense are unchanged. Miners vacate planned build tiles through
the completed inward network and stage on long conveyor chains. A single
terrain/start predicate restores exact parent movement wherever paired tests
showed a regression; no opening is scripted.

Paired 10 ms results over all 53 maps and both seats:

- Spar Econ: 23-83 versus the parent's 22-84 (Fjord A gained, no losses);
- Brokkr: 24-82 for both;
- Steward: 17-89 for both;
- direct parent matchup: one Sprint A gain, no losses.

An initial transplant was only +1 over 318 opponent games because Crossfire A
lost while Fjord A and Quarry B gained. The final full-fallback gate restores
Crossfire and all previously identified sensitive starts byte-for-byte; Quarry's
directed-vacate-only gain is deliberately surrendered rather than accepting a
known regression. Net final opponent-panel delta is +1 with no paired loss.

The online target list uses the current upper neighborhood, led by Bean counters,
rather than the older v120 opponent slice. Promotion remains ladderfarm's
qualified expected-Elo decision.
