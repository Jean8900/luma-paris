# Brouillon 20/11

- Éventuellement créer une seconde adresse mail et un second compte Luma, pour tester sans risquer le compte principal.
- Problème : get-items répond 401 « You are not signed in » à nos requêtes anonymes, alors que les 18 premiers backfills ont réussi. Aucune auth envoyée. Limite Luma non documentée.
- Analyse 401 : get-items renvoie {"message":"You are not signed in."} pour Curiosity (cal-0FvXA0LuBabcAFy), identique aux 401 génériques, donc non discriminant. La page lu.ma/curiosity_team contient <h3>This is a members-only calendar.</h3> (HTML rendu côté serveur, absent de lu.ma/aisalon). Correctif codé : sur StopBackfill(code=401), si is_members_only(url) (1 requête page) alors backfilled=Membres puis on continue ; sinon arrêt comme avant. Pas encore exécuté.
