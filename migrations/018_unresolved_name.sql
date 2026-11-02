-- The unmatched holdings' node, in plain words (Impeccable critique, 2026-11-01).
--
-- "Unresolved Holdings" is the pipeline's word for it; on a fund's holdings it
-- sat beside HDFC Bank and ITC as if it were a company. The id, which every
-- query and the look-through engine key on, is unchanged.
UPDATE issuer SET canonical_name = 'Not matched to a company'
 WHERE issuer_id = '__UNRESOLVED__';
