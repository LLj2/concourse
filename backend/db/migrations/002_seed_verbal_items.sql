-- Concourse — initial verbal reasoning item bank
-- 8 items across difficulty 1-3, EPSO-style "passage + inference" format.
-- These are measurement items, not exam simulations — kept short by design.
-- Idempotent: safe to re-run.

-- We use deterministic UUIDs so re-running doesn't insert duplicates.
-- (Postgres' uuid-ossp/uuid v5 would be cleaner; we use plain text->md5 here.)

with new_items(slug, difficulty, prompt, options, correct_index, explanation) as (values

  -- difficulty 1 (easy) ---------------------------------------------------
  ('v1_eu_official_languages', 1,
   'The European Union currently has 24 official languages. Each Member State, when joining, designates one or more official languages from those of its territory. Irish was granted full official status in 2022.',
   '["The EU has had 24 official languages since 2022.","Irish became fully official in 2022.","Every official language corresponds to exactly one Member State.","All 24 languages were granted equal status only when Ireland joined."]'::jsonb,
   1,
   'The passage states explicitly that Irish was granted full official status in 2022. The other options either overstate (1, 4) or contradict (3, since several languages map to multiple Member States) what the text supports.'),

  ('v1_council_voting', 1,
   'The Council of the EU adopts most legislative acts by qualified majority voting. A qualified majority requires at least 55% of Member States, representing at least 65% of the EU population. Some sensitive areas, such as taxation, still require unanimity.',
   '["Taxation can be decided by qualified majority.","Qualified majority requires 65% of Member States.","Unanimity is no longer used in the Council.","The Council uses qualified majority voting for most legislative acts."]'::jsonb,
   3,
   'The text says most acts are adopted by qualified majority. The other options misstate the thresholds (option 2 swaps 55% and 65%) or contradict the passage on unanimity (1, 3).'),

  ('v1_horizon_europe', 1,
   'Horizon Europe is the EU framework programme for research and innovation for 2021-2027, with a budget of around 95 billion euros. It funds collaborative research between universities, businesses, and public bodies across Member States and associated countries.',
   '["Horizon Europe is restricted to EU Member States only.","Horizon Europe runs from 2021 to 2027.","Horizon Europe is a national research programme.","Horizon Europe primarily funds individual researchers, not collaborations."]'::jsonb,
   1,
   'Option 2 (i.e. correct_index 1) is directly stated. Option 1 is contradicted by the mention of associated countries; option 3 is contradicted by "EU framework programme"; option 4 is contradicted by "collaborative research."'),

  -- difficulty 2 (medium) -------------------------------------------------
  ('v2_etias_purpose', 2,
   'The European Travel Information and Authorisation System (ETIAS) is a pre-travel screening for visa-exempt non-EU travellers entering the Schengen Area. It is not a visa: travellers complete an online form and pay a fee, and a decision is normally returned within minutes. ETIAS does not apply to citizens of EU Member States or to non-EU citizens already holding a Schengen residence permit.',
   '["ETIAS replaces the Schengen visa for all non-EU travellers.","ETIAS applies to EU citizens travelling within Schengen.","ETIAS is unnecessary for non-EU citizens with a Schengen residence permit.","ETIAS authorisations always require manual review and take several days."]'::jsonb,
   2,
   'The passage says ETIAS does not apply to non-EU citizens already holding a Schengen residence permit. Option 1 is wrong because ETIAS is explicitly distinguished from a visa; option 2 contradicts the exemption for EU citizens; option 4 contradicts "decision normally returned within minutes."'),

  ('v2_eu_carbon_market', 2,
   'The EU Emissions Trading System (ETS) caps the total greenhouse gas emissions allowed from covered installations and lets participants trade allowances. The cap is reduced each year, which is intended to push the carbon price upwards over time. Sectors not covered by the ETS, such as buildings and road transport, will be addressed by a separate ETS2 starting in 2027.',
   '["The ETS cap rises each year to expand coverage.","ETS2 will cover buildings and road transport.","Buildings are already part of the original ETS.","ETS2 starts in 2025."]'::jsonb,
   1,
   'The passage states ETS2 will cover sectors like buildings and road transport. Option 1 is contradicted ("cap is reduced each year"); option 3 is contradicted ("Sectors not covered by the ETS, such as buildings"); option 4 misstates the year.'),

  ('v2_subsidiarity', 2,
   'Under the principle of subsidiarity, the EU acts in areas of shared competence only when the objectives of the proposed action cannot be sufficiently achieved by the Member States, but can be better achieved at Union level. National parliaments can issue a reasoned opinion if they consider a draft EU act breaches the principle.',
   '["Subsidiarity applies when the EU has exclusive competence.","National parliaments can challenge an EU act they consider breaches subsidiarity.","Member States cannot legislate in areas where subsidiarity is invoked.","Subsidiarity allows the EU to act whenever it chooses."]'::jsonb,
   1,
   'The passage explicitly states national parliaments can issue a reasoned opinion if they consider an act breaches subsidiarity. Option 1 is wrong (subsidiarity applies to shared, not exclusive competence); option 3 misstates it; option 4 contradicts the conditional nature of EU action under subsidiarity.'),

  -- difficulty 3 (hard) ---------------------------------------------------
  ('v3_neighbourhood_policy', 3,
   'The European Neighbourhood Policy (ENP) governs relations between the EU and 16 of its closest neighbours to the East and South. While the ENP offers political association and economic integration, it does not prejudge the future relationship with any partner country, and is distinct from the enlargement process. Some ENP partners have, however, subsequently been granted candidate status through separate Council decisions.',
   '["The ENP guarantees eventual EU membership to its partner countries.","Candidate status, when granted to ENP partners, comes through the same legal track as the ENP itself.","The ENP and the enlargement process are formally distinct, although individual countries may move from one to the other.","The ENP applies only to the EU''s southern neighbours."]'::jsonb,
   2,
   'The passage says the ENP is distinct from the enlargement process and that some partners have been granted candidate status through separate Council decisions, supporting option 3 (correct_index 2). Option 1 is contradicted by "does not prejudge the future relationship"; option 2 contradicts "separate Council decisions"; option 4 ignores the East-and-South scope.'),

  ('v3_court_of_justice', 3,
   'The Court of Justice of the European Union ensures that EU law is interpreted and applied uniformly across Member States. It rules on preliminary references from national courts, infringement proceedings brought by the Commission against Member States, and actions for annulment of EU acts. The Court does not, however, rule on the compatibility of national law with national constitutions; that remains the responsibility of national constitutional courts.',
   '["The Court of Justice can review whether a national law complies with the constitution of that Member State.","Preliminary references are submitted by national courts seeking interpretation of EU law.","Infringement proceedings are initiated by individuals against Member States.","Actions for annulment apply only to acts of national parliaments."]'::jsonb,
   1,
   'The passage states the Court of Justice rules on preliminary references from national courts (correct_index 1). Option 1 is directly contradicted; option 3 misstates who can initiate (the Commission, not individuals); option 4 misstates the scope of annulment actions (EU acts, not national).')

),
inserted as (
  insert into items (id, skill_id, difficulty, prompt, options, correct_index, explanation, source, archived)
  select md5(slug)::uuid, 'verbal', difficulty, prompt, options, correct_index, explanation, 'authored', false
  from new_items
  on conflict (id) do nothing
  returning id
)
select count(*) || ' verbal items inserted' as result from inserted;
