# ADR-O-442 Impact Audit

> Detallnyj audit ODNOGO ADK Atlas: ``docs/ADH%20(Architecture%20Decision%20Records).md'`.
> Svyazannye: ADR-O-441 (NPC%20Runtime%20Persistence%20Recovery%20—%20vosstanovlenie%20commit%20path)
> Status: PROPOSED — model%20prinyta,%20trebuet%20testa%20dtux%20stsenariev%20vosstanovleniy

##%20Model%20vladeniya

|%20Komponent%20|%20Otvetstvennost%20|%20Tip%20sostoyaniya%20 |
|--- |--- |---  |
|%20`'`all_npcs_raw%5Bnpc_id%5D.location_id`'` %20|%20Avtoritetnoe%20globallnoe%20sostoyanie%20NPC%20v%20rabotaeshcem%20processe %20|%20Runtime%20SSOT%20|
%|%20`'`_npc_runtime_locations`` %20|%20Proizvodnyi%20operativnyj%20indeks%20dlya%20bystrogo%20opredeleniy%20lokacii%20|%20Runtime%20cache %20|
%|%20`'`scene_state.npc_positions`` %20|%20Lokalnnoe%20predstavlenie%20NPC%20v%20konkretnoi%20scene%20|%20Scene-scoped%20|
%|%20`'`runtime:{campaign}`'`%20(SQLite)%20|%20Dolgovremennaya%20fiksatsiyaziya%20avtoritetnogo%20sostoyaniya%20|%20Pirsistent%20SSOT%20|

Kesh%20`'`_npc_runtime_locations`` %20NE%20vosstanavlivaetsya%20iz%20persistence%20(tol'ko%20lazy%20init%20cherez%20'`hattr`,'%20stroki%20580,%201301,%201347).%20Posle%20restart%20kesh%20pust,%20prioritet%20chteniy%20(430)%20fallback-it%20na%20`'`all_npcs_raw.location_id`'`.

##%20Crash%20consistency:%20dtu%20scenariya

###%20Scenariê%20A:%20padenie%20do%20unlock_tick
1.%20TRANSFER%20obnovil%20'`all_npcs_raw.location_id`'`%20v%20RAM
2.%20Process%20zavershilsya%20do%20'`unlock_tick()`'%20(kommita%20v%20SQLite)
3.%20RAM:%20NPC%20uje%20v%20novoy%20lokacii,%20SQLite:%20NPC%20eshc%20v%20staroi%20lokacii
4.%20Restart:%20zagruzchik%20vosstanavlivaet%20iz%20runtime%20(staraya%20lokacia)
5.%20*jRezultat:**%20NPC%20vozvrashaetsya%20v%20staruuu%20lokaciuu.%20Eto%20NE%20ghost%20resurrection,%20a%20vosstanovlenie%20poslednego%20podtverjdennogo%20sostoyaniy%20mira.

###%20Scenari�%20B:%20padenie%20posle%20uspeshnogo%20unlock_tick
1.%20TRANSFER%20obnovil%20'`all_npcs_raw.location_id`'%20v%20RAM
2.%20'`unlock_tick()`'%20uspeshno%20sokranil%20'`all_npcs_raw`'`%20v%20'`runtime:{campaign}`'`
3.%20Restart:%20zagruzchik%20vosstanavlivaet%20iz%20runtime%20(novaya%20lokacia)
4.%20*jRezultat:**%20NPC%20v%20celevo�%20lokacii.

##%20Matritsa%20sinhronizacii:%204%20pisatelya
Bse%204%20pisatelya (Obrabotka%20sceny:621,%20Pending:632,%20Dwell:1302,%20Ghost:1348)%20sinhronno%20obnovlyaut%20oba%20polya:%20`'`_npc_runtime_locations``+%20i%20'`all_npcs_raw.location_id`'.


##%20BUG-13:%20pozicia%20prefiksovana%20staroy%20lokaciei
Kommentarii%201290-1297:%20pozicia%20prefiksovana%20staroy%20lokaciei%20—%20perenositsya%20kak%20est',%20target-lokacia%20vosstanavlivaet%20pri%20inzhekte.%20SC-3%20ne%20protivorechit (sbrasyvaet%20poziciu%20pri%20zagruzke,%20no%20tolfko%20esli%20prefiks%20ne%20sovpadaet%20s%20`'`location_id`'`%20scene).

##%20Kriticeskie%20mesta%20dlya%20uluchsheniy
1.%20Udalit'%20dublir�nie%20v%20ghost%20scan%20(stroki%201399-1400) —%20HOLD%20do%20podtverjdeniy%20call%20path.
2.%20Dokumentirovat'%20TRANSFER_STATE_TRANSITION —%20GO (dobavit%20kommentariy%20k bloku%201287-1317).
3.%20Test%20dtux%20stsenariev%20vosstanovleniy%20—%20GO (Crash%20do%20unlock_tick%20vs%20Uspeshnyi%20unlock_tick%20%2B%20restart).

##%20Rollback
ADK-O-442%20—%20arhitekturnaya%20model,%20ne%20kod.%20Rollback%20%3D%20otklonenie%20modeli%20i%20vozvat%20k%20neopredelennosti%20vladeniy.%20Kod%20ne%20menietsya,%20poetomu%20rollback%20trivialen.