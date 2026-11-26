"""Internationalization (ru / kk / en) message catalog and rendering helpers."""

from __future__ import annotations

from typing import Any, Literal

Lang = Literal["ru", "kk", "en"]
DEFAULT_LANG: Lang = "ru"
SUPPORTED_LANGS: tuple[Lang, ...] = ("ru", "kk", "en")


MESSAGES: dict[str, dict[Lang, str]] = {
    # --- Precheck & IIK validation messages ---
    "rule.invalid_bin": {
        "ru": "В БИН/ИИН получателя ошибка — такого номера не существует.",
        "kk": "Алушының БСН/ЖСН-інде қате бар — мұндай нөмір жоқ.",
        "en": "The recipient's BIN/IIN is invalid — this number does not exist.",
    },
    "iik.empty": {
        "ru": "Укажите ИИК счёта.",
        "kk": "Шоттың ЖСК (ИИК) нөмірін көрсетіңіз.",
        "en": "Please enter the account IIK (IBAN).",
    },
    "iik.cyrillic": {
        "ru": "В ИИК найдены кириллические буквы вместо латинских — проверьте раскладку.",
        "kk": "ЖСК-да латын әріптерінің орнына кириллица әріптері бар — пернетақта тілін тексеріңіз.",
        "en": "The IIK contains Cyrillic letters instead of Latin ones — check your keyboard layout.",
    },
    "iik.length": {
        "ru": "ИИК должен состоять из 20 символов (сейчас {length}).",
        "kk": "ЖСК 20 таңбадан тұруы тиіс (қазір {length}).",
        "en": "The IIK must be 20 characters long (currently {length}).",
    },
    "iik.uppercase": {
        "ru": "ИИК должен быть записан только заглавными латинскими буквами и цифрами.",
        "kk": "ЖСК тек латын алфавитінің бас әріптері мен цифрлардан тұруы тиіс.",
        "en": "The IIK must contain only uppercase Latin letters and digits.",
    },
    "iik.prefix_kz": {
        "ru": "ИИК казахстанского счёта должен начинаться с KZ.",
        "kk": "Қазақстандық шоттың ЖСК нөмірі KZ таңбаларынан басталуы тиіс.",
        "en": "A Kazakhstan account IIK must start with KZ.",
    },
    "iik.alnum": {
        "ru": "ИИК должен содержать только заглавные латинские буквы и цифры без пробелов.",
        "kk": "ЖСК бос орынсыз тек латын алфавитінің бас әріптері мен цифрлардан тұруы тиіс.",
        "en": "The IIK must contain only uppercase Latin letters and digits without spaces.",
    },
    "iik.check_digits": {
        "ru": "В ИИК указаны неверные контрольные цифры после KZ.",
        "kk": "ЖСК-да KZ-тен кейінгі бақылау цифрлары қате көрсетілген.",
        "en": "The check digits after KZ in the IIK are invalid.",
    },
    "iik.checksum": {
        "ru": "В ИИК ошибка контрольной суммы — такого счёта не существует.",
        "kk": "ЖСК-ның бақылау сомасында қате бар — мұндай шот жоқ.",
        "en": "The IIK checksum is invalid — this account does not exist.",
    },
    "iik.bank_code_digits": {
        "ru": "В ИИК указан неверный код банка — символы 5–7 должны быть цифрами.",
        "kk": "ЖСК-да банк коды қате көрсетілген — 5–7-таңбалар цифрлар болуы тиіс.",
        "en": "The bank code in the IIK is invalid — characters 5–7 must be digits.",
    },
    "iik.unknown_bank_code": {
        "ru": "Неизвестный код банка ({code}) в ИИК — такого счёта не существует.",
        "kk": "ЖСК-дағы банк коды ({code}) белгісіз — мұндай шот жоқ.",
        "en": "Unknown bank code ({code}) in the IIK — this account does not exist.",
    },
    "rule.invalid_iik_fallback": {
        "ru": "В ИИК ошибка — такого счёта не существует.",
        "kk": "ЖСК-да қате бар — мұндай шот жоқ.",
        "en": "The IIK is invalid — this account does not exist.",
    },
    "rule.invalid_bik": {
        "ru": "Указан неверный или неизвестный БИК банка получателя.",
        "kk": "Алушы банкінің БСК (БИК) коды қате немесе белгісіз.",
        "en": "The recipient bank's BIK is invalid or unknown.",
    },
    "rule.iik_bank_code_vs_bik": {
        "ru": "Код банка в номере счёта не совпадает с указанным БИК.",
        "kk": "Шот нөміріндегі банк коды көрсетілген БСК-ға (БИК) сәйкес келмейді.",
        "en": "The bank code in the account number does not match the specified BIK.",
    },
    "rule.bcc_account_not_found": {
        "ru": "Счёт в BCC не найден.",
        "kk": "Шот BCC-де табылмады.",
        "en": "This BCC account was not found.",
    },
    # --- Risk scoring rule messages ---
    "rule.bcc_account_other_owner": {
        "ru": "Счёт в BCC оформлен не на указанного получателя.",
        "kk": "BCC-дегі шот көрсетілген алушыға рәсімделмеген.",
        "en": "This BCC account is not registered to the specified recipient.",
    },
    "analyst.bcc_account_other_owner": {
        "ru": (
            "Этот счёт в BCC оформлен на другую компанию ({owner_name}, БИН {owner_bin}), "
            "а не на указанного получателя."
        ),
        "kk": (
            "BCC-дегі бұл шот көрсетілген алушыға емес, "
            "басқа компанияға ({owner_name}, БСН {owner_bin}) рәсімделген."
        ),
        "en": (
            "This BCC account is registered to another company ({owner_name}, BIN {owner_bin}), "
            "not the stated recipient."
        ),
    },
    "rule.lookalike_supplier": {
        "ru": (
            "Название получателя почти совпадает с вашим поставщиком {supplier_name}, "
            "но указан другой БИН."
        ),
        "kk": (
            "Алушының атауы сіздің жеткізушіңізбен ({supplier_name}) дерлік бірдей, "
            "бірақ басқа БСН көрсетілген."
        ),
        "en": (
            "The recipient name closely resembles your supplier {supplier_name}, "
            "but has a different BIN."
        ),
    },
    "rule.lookalike_supplier_exact": {
        "ru": (
            "Название получателя совпадает с вашим поставщиком {supplier_name}, "
            "но указан другой БИН — у действующей компании БИН не меняется."
        ),
        "kk": (
            "Алушының атауы сіздің жеткізушіңізбен ({supplier_name}) сәйкес келеді, "
            "бірақ басқа БСН көрсетілген — заңды тұлғаның БСН-і өзгермейді."
        ),
        "en": (
            "The recipient name matches your supplier {supplier_name}, "
            "but a different BIN was entered — a company's BIN never changes."
        ),
    },
    "rule.mixed_script_name": {
        "ru": "В названии получателя есть символы другого алфавита или цифры вместо букв.",
        "kk": "Алушының атауында басқа әліпби таңбалары немесе әріп орнына цифрлар бар.",
        "en": "The recipient name contains characters from another alphabet or digits used in place of letters.",
    },
    "analyst.mixed_script_name": {
        "ru": "Обнаружены подозрительные символы в названии на позициях: {positions}.",
        "kk": "Алушы атауында күдікті таңбалар табылды (орындары: {positions}).",
        "en": "Suspicious characters detected in recipient name at positions: {positions}.",
    },
    "rule.bin_name_mismatch_history": {
        "ru": (
            "По этому БИН в реестре указано название {registered_name}, "
            "но вы уже платили на этот счёт."
        ),
        "kk": (
            "Бұл БСН бойынша тізілімде {registered_name} атауы көрсетілген, "
            "бірақ сіз бұл шотқа бұрын төлем жасағансыз."
        ),
        "en": (
            "The registry lists {registered_name} under this BIN, "
            "but you have paid this account before."
        ),
    },
    "rule.bin_name_mismatch": {
        "ru": "По этому БИН в реестре числится другая компания — {registered_name}.",
        "kk": "Бұл БСН бойынша тізілімде басқа компания тіркелген — {registered_name}.",
        "en": "A different company is registered under this BIN — {registered_name}.",
    },
    "rule.iik_belongs_to_other_counterparty": {
        "ru": "Этот счёт раньше принадлежал вашему поставщику {other_name}.",
        "kk": "Бұл шот бұрын сіздің жеткізушіңізге ({other_name}) тиесілі болған.",
        "en": "This account previously belonged to your supplier {other_name}.",
    },
    "rule.iik_changed": {
        "ru": "У этого поставщика указан новый номер счёта, на который вы раньше не платили.",
        "kk": "Бұл жеткізушінің жаңа шот нөмірі көрсетілген, сіз оған бұрын төлем жасамағансыз.",
        "en": "This supplier has a new account number that you have not paid before.",
    },
    "rule.bank_changed": {
        "ru": "Сменился банк поставщика: раньше платежи шли в {old_bank}, а теперь в {new_bank}.",
        "kk": "Жеткізушінің банкі өзгерген: бұрын төлемдер мына банкке жіберілген — {old_bank}, қазір — {new_bank}.",
        "en": "The supplier's bank changed: previous payments went to {old_bank}, now to {new_bank}.",
    },
    "rule.entity_type_mismatch_legal_iin": {
        "ru": "В названии указана компания, но вместо БИН введён ИИН физлица.",
        "kk": "Атауда заңды тұлға көрсетілген, бірақ БСН орнына жеке тұлғаның ЖСН-і енгізілген.",
        "en": "The name indicates a legal entity, but an individual's IIN was entered instead of a BIN.",
    },
    "rule.entity_type_mismatch_ie_bin": {
        "ru": "В названии указан ИП, но вместо ИИН введён БИН юрлица.",
        "kk": "Атауда ЖК көрсетілген, бірақ ЖСН орнына заңды тұлғаның БСН-і енгізілген.",
        "en": "The name indicates an individual entrepreneur, but a corporate BIN was entered instead of an IIN.",
    },
    "rule.kbe_mismatch_legal_iin": {
        "ru": "Указан КБе 17 (юрлицо), но вместо БИН введён ИИН физлица.",
        "kk": "КБе 17 (заңды тұлға) көрсетілген, бірақ БСН орнына жеке тұлғаның ЖСН-і енгізілген.",
        "en": "KBe 17 (legal entity) was specified, but an individual's IIN was entered instead of a BIN.",
    },
    "rule.kbe_mismatch_individual_bin": {
        "ru": "Указан КБе 19 (физлицо/ИП), но вместо ИИН введён БИН юрлица.",
        "kk": "КБе 19 (жеке тұлға/ЖК) көрсетілген, бірақ ЖСН орнына заңды тұлғаның БСН-і енгізілген.",
        "en": "KBe 19 (individual/IE) was specified, but a corporate BIN was entered instead of an IIN.",
    },
    "rule.knp_unusual": {
        "ru": "Указан непривычный КНП ({actual_knp}) для этого поставщика — обычно используется {expected_knp}.",
        "kk": "Бұл жеткізуші үшін әдеттен тыс КНП ({actual_knp}) көрсетілген — әдетте {expected_knp} қолданылады.",
        "en": "Unusual KNP ({actual_knp}) for this supplier — typically {expected_knp}.",
    },
    "rule.new_bcc_account": {
        "ru": "Счёт получателя открыт недавно.",
        "kk": "Алушының шоты жақында ашылған.",
        "en": "The recipient's account was opened recently.",
    },
    "analyst.new_bcc_account": {
        "ru": "Счёт в BCC открыт недавно — {age_days} дн. назад ({opened_at}).",
        "kk": "BCC-дегі шот жақында ашылған — {age_days} күн бұрын ({opened_at}).",
        "en": "This BCC account was opened recently — {age_days} days ago ({opened_at}).",
    },
    "rule.amount_anomaly_first_p90": {
        "ru": (
            "Сумма первого платежа новому поставщику выше 90% ваших прошлых платежей "
            "(обычно не более {client_p90_kzt})."
        ),
        "kk": (
            "Жаңа жеткізушіге алғашқы төлем сомасы бұрынғы төлемдеріңіздің 90%-ынан жоғары "
            "(әдетте {client_p90_kzt} аспайды)."
        ),
        "en": (
            "This first payment to a new supplier exceeds 90% of your past payments "
            "(usually up to {client_p90_kzt})."
        ),
    },
    "rule.amount_anomaly_supplier": {
        "ru": (
            "Сумма платежа в {ratio} раза выше обычной для этого поставщика "
            "(обычно около {median_kzt})."
        ),
        "kk": (
            "Төлем сомасы осы жеткізуші үшін әдеттегіден {ratio} есе жоғары "
            "(әдетте шамамен {median_kzt})."
        ),
        "en": (
            "The payment amount is {ratio}x higher than usual for this supplier "
            "(typically around {median_kzt})."
        ),
    },
    "rule.first_payment": {
        "ru": "Вы ещё ни разу не платили этому поставщику — сравнить реквизиты не с чем.",
        "kk": "Сіз бұл жеткізушіге бұрын төлем жасамағансыз — деректемелерді салыстыратын тарих жоқ.",
        "en": "You have never paid this supplier before — there is no history to compare requisites against.",
    },
    "rule.bin_young": {
        "ru": "Компания зарегистрирована недавно — менее года назад ({reg_date}).",
        "kk": "Компания жақында тіркелген — бір жылдан аз уақыт бұрын ({reg_date}).",
        "en": "The company was registered recently — less than a year ago ({reg_date}).",
    },
    "rule.urgent_wording": {
        "ru": (
            "В назначении платежа есть формулировка срочности или смены реквизитов — "
            "частый признак подмены счёта."
        ),
        "kk": (
            "Төлем мақсатында шұғылдық немесе деректемелердің өзгеруі туралы сөздер бар — "
            "бұл шотты алмастырудың жиі белгісі."
        ),
        "en": (
            "The payment purpose mentions urgency or changed requisites — "
            "a common sign of invoice fraud."
        ),
    },
    "rule.trusted_account": {
        "ru": "Новый счёт подтверждён директором {date_label}.",
        "kk": "Жаңа шотты директор {date_label} күні растады.",
        "en": "The new account was confirmed by the director on {date_label}.",
    },
    "rule.bcc_owner_verified": {
        "ru": "Счёт подтверждён банком: принадлежит этому поставщику.",
        "kk": "Шот банкпен расталған: осы жеткізушіге тиесілі.",
        "en": "Account verified by the bank: belongs to this supplier.",
    },
    # --- Bank-wide cross-client anonymized risk rules ---
    "rule.iik_reported_by_clients": {
        "ru": "На этот счёт уже поступали жалобы от других клиентов банка.",
        "kk": "Бұл шотқа банктің басқа клиенттерінен бұрын шағымдар түскен.",
        "en": "Other clients of the bank have previously reported this account.",
    },
    "rule.iik_reported_by_clients_many": {
        "ru": "На этот счёт поступило несколько (3+) жалоб о мошенничестве от других клиентов банка.",
        "kk": "Бұл шотқа банктің басқа клиенттерінен алаяқтық туралы бірнеше (3+) шағым түскен.",
        "en": "Multiple (3+) other clients of the bank have reported this account for fraud.",
    },
    "analyst.iik_reported_by_clients": {
        "ru": (
            "По счёту зафиксировано жалоб от других клиентов BCC: {count} "
            "(последняя: {last_reported_at})."
        ),
        "kk": (
            "Бұл шот бойынша BCC-дің басқа клиенттерінен тіркелген шағымдар саны: {count} "
            "(соңғысы: {last_reported_at})."
        ),
        "en": (
            "Other BCC clients submitted {count} fraud report(s) on this account "
            "(latest: {last_reported_at})."
        ),
    },
    "rule.iik_on_watchlist": {
        "ru": "Счёт получателя находится в списке подозрительных (дропперских) счетов антифрод-центра.",
        "kk": "Алушының шоты антифрод-орталықтың күдікті (дропперлік) шоттар тізімінде тұр.",
        "en": "The recipient's account is listed on the antifraud center's suspicious (mule) account watchlist.",
    },
    "analyst.iik_on_watchlist": {
        "ru": (
            "Счёт числится в списке подозрительных счетов: {source} "
            "(категория: {category}, добавлен: {added_at})."
        ),
        "kk": (
            "Шот күдікті шоттар тізімінде тұр: {source} "
            "(санат: {category}, қосылған күні: {added_at})."
        ),
        "en": (
            "Account is listed on watchlist: {source} "
            "(category: {category}, added: {added_at})."
        ),
    },
    "rule.fresh_iik_many_payers": {
        "ru": (
            "Этот новый счёт за последние дни впервые получил платежи "
            "от нескольких (3+) не связанных компаний."
        ),
        "kk": (
            "Бұл жаңа шот соңғы күндері өзара байланысы жоқ бірнеше (3+) "
            "компаниядан алғаш рет төлемдер алған."
        ),
        "en": (
            "Over the past few days, this new account received first-time payments "
            "from several (3+) unrelated companies."
        ),
    },
    "rule.fresh_iik_many_payers_many": {
        "ru": (
            "Этот новый счёт за последние дни впервые получил платежи "
            "от многих (5+) не связанных компаний."
        ),
        "kk": (
            "Бұл жаңа шот соңғы күндері өзара байланысы жоқ көптеген (5+) "
            "компаниядан алғаш рет төлемдер алған."
        ),
        "en": (
            "Over the past few days, this new account received first-time payments "
            "from many (5+) unrelated companies."
        ),
    },
    "analyst.fresh_iik_many_payers": {
        "ru": (
            "За последние {window_days} дн. на счёт поступили первые платежи от "
            "{distinct_payers} не связанных клиентов BCC на сумму {total_kzt}."
        ),
        "kk": (
            "Соңғы {window_days} күнде осы шотқа BCC-дің өзара байланысы жоқ "
            "{distinct_payers} клиентінен {total_kzt} сомасына алғашқы төлемдер түскен."
        ),
        "en": (
            "Over the past {window_days} days, {distinct_payers} unrelated BCC clients "
            "made first-time payments to this account totaling {total_kzt}."
        ),
    },
    "rule.duplicate_invoice": {
        "ru": "Возможна повторная оплата счёта № {invoice_no} (уже встречался {prev_date}).",
        "kk": "№ {invoice_no} төлем шотын қайта төлеу мүмкін (бұрын {prev_date} кездескен).",
        "en": "Possible duplicate payment for invoice #{invoice_no} (previously seen on {prev_date}).",
    },
    "rule.new_recipient_accumulated": {
        "ru": (
            "Накопленная сумма новому получателю за 7 дней составила {total_kzt} "
            "(операций: {count})."
        ),
        "kk": (
            "Жаңа алушыға 7 күнде жинақталған жалпы сома {total_kzt} құрады (операциялар: {count})."
        ),
        "en": (
            "Accumulated amount to this new recipient over 7 days reached {total_kzt} "
            "({count} checks/payments)."
        ),
    },
    "rule.structuring_72h": {
        "ru": (
            "За 72 часа накопилось {count} платежа этому получателю на сумму {total_kzt} "
            "({ratio}× от обычной суммы) — возможно дробление платежа."
        ),
        "kk": (
            "72 сағат ішінде осы алушыға жалпы сомасы {total_kzt} болатын {count} төлем жасалды "
            "(әдеттегіден {ratio} есе көп) — төлемді бөлшектеу белгісі болуы мүмкін."
        ),
        "en": (
            "{count} payments to this recipient within 72 hours total {total_kzt} "
            "({ratio}x typical amount) — possible payment splitting."
        ),
    },
    # --- Verdict headlines ---
    "headline.green": {
        "ru": "Всё как раньше",
        "kk": "Бәрі бұрынғыдай",
        "en": "Everything matches history",
    },
    "headline.green_with_amplifiers": {
        "ru": "Реквизиты знакомые, но есть замечания",
        "kk": "Деректемелер таныс, бірақ ескертулер бар",
        "en": "Known requisites, with minor notes",
    },
    "headline.green_trusted": {
        "ru": "Счёт подтверждён директором",
        "kk": "Шотты директор растаған",
        "en": "Account confirmed by director",
    },
    "headline.green_budget": {
        "ru": "Бюджетный платёж: реквизиты казначейства верны",
        "kk": "Бюджеттік төлем: қазынашылық деректемелері дұрыс",
        "en": "Budget payment: treasury requisites are valid",
    },
    "headline.green_bank_verified": {
        "ru": "Счёт подтверждён банком: принадлежит этому поставщику",
        "kk": "Шот банкпен расталған: осы жеткізушіге тиесілі",
        "en": "Account verified by the bank: belongs to this supplier",
    },
    "headline.yellow": {
        "ru": "Есть изменения",
        "kk": "Өзгерістер бар",
        "en": "Changes detected",
    },
    "headline.red": {
        "ru": "Похоже на подмену",
        "kk": "Деректемелер алмастырылған сияқты",
        "en": "Likely requisite substitution",
    },
    "headline.grey": {
        "ru": "Нет истории для сравнения",
        "kk": "Салыстыратын төлем тарихы жоқ",
        "en": "No payment history to compare",
    },
    "headline.invalid": {
        "ru": "Ошибка в реквизитах",
        "kk": "Деректемелерде қате бар",
        "en": "Invalid payment requisites",
    },
    # --- Recommended next actions ---
    "next_action.green": {
        "ru": "Реквизиты и сумма совпадают с вашей историей платежей — можно подписывать.",
        "kk": "Деректемелер мен сома төлем тарихыңызға сәйкес келеді — қол қоюға болады.",
        "en": "Requisites and amount match your payment history — safe to sign.",
    },
    "next_action.green_with_amplifiers": {
        "ru": "Реквизиты поставщика знакомые, но проверьте замечания ниже перед подписанием.",
        "kk": "Жеткізушінің деректемелері таныс, бірақ қол қоймас бұрын төмендегі ескертулерді тексеріңіз.",
        "en": "Supplier requisites are familiar, but review the notes below before signing.",
    },
    "next_action.green_budget": {
        "ru": "Реквизиты казначейства проверены — бюджетный платёж можно подписывать.",
        "kk": "Қазынашылық деректемелері тексерілді — бюджеттік төлемге қол қоюға болады.",
        "en": "Treasury requisites are verified — this budget payment is safe to sign.",
    },
    "next_action.green_bank_verified": {
        "ru": "Новый счёт в BCC подтверждён банком как принадлежащий этому поставщику — можно подписывать.",
        "kk": "BCC-дегі жаңа шот осы жеткізушіге тиесілі екені банкпен расталды — қол қоюға болады.",
        "en": "This new BCC account is verified by the bank as belonging to this supplier — safe to sign.",
    },
    "next_action.amount_only": {
        "ru": "Сумма необычно большая для этого поставщика: проверьте счёт и договор.",
        "kk": "Бұл жеткізуші үшін сома әдеттен тыс үлкен: төлем шоты мен шартты тексеріңіз.",
        "en": "The amount is unusually large for this supplier: check the invoice and contract.",
    },
    "next_action.duplicate_invoice": {
        "ru": "Возможна повторная оплата счёта: сверьте номер счёта с уже проведёнными платежами.",
        "kk": "Төлем шотын қайта төлеу мүмкін: төлем шотының нөмірін бұрын өткізілген төлемдермен салыстырыңыз.",
        "en": "Possible duplicate invoice payment: check the invoice number against prior payments.",
    },
    "next_action.yellow": {
        "ru": (
            "Позвоните поставщику по номеру из договора, "
            "а не из письма с новыми реквизитами, и подтвердите счёт."
        ),
        "kk": (
            "Жаңа деректемелер келген хаттағы емес, шарттағы телефон нөмірі бойынша "
            "жеткізушіге хабарласып, шот деректемелерін растаңыз."
        ),
        "en": (
            "Call the supplier using the phone number from your contract, "
            "not the email with new details, and confirm the account."
        ),
    },
    "next_action.red": {
        "ru": (
            "Не подписывайте платёж. Позвоните поставщику по номеру из договора, "
            "а не из письма с новыми реквизитами."
        ),
        "kk": (
            "Төлемге қол қоймаңыз. Жаңа деректемелер келген хаттағы емес, "
            "шарттағы телефон нөмірі бойынша жеткізушіге хабарласыңыз."
        ),
        "en": (
            "Do not sign this payment. Call the supplier using the phone number from your contract, "
            "not the email with new details."
        ),
    },
    "next_action.grey": {
        "ru": "Проверьте БИН поставщика в реестре и подтвердите реквизиты по телефону из договора.",
        "kk": "Жеткізушінің БСН-ін тізілімнен тексеріп, деректемелерді шарттағы телефон нөмірі арқылы растаңыз.",
        "en": "Verify the supplier's BIN in the registry and confirm requisites by the phone number from your contract.",
    },
    "next_action.grey_above_p90": {
        "ru": (
            "Крупный первый платёж новому поставщику: проверьте БИН в реестре, "
            "подтвердите реквизиты по телефону из договора и согласуйте с директором."
        ),
        "kk": (
            "Жаңа жеткізушіге ірі алғашқы төлем: БСН-ін тізілімнен тексеріп, "
            "деректемелерді шарттағы телефон нөмірі арқылы растап, директормен келісіңіз."
        ),
        "en": (
            "Large first payment to a new supplier: verify the BIN in the registry, "
            "confirm requisites by the contract phone number, and get director approval."
        ),
    },
    "next_action.invalid": {
        "ru": "Исправьте реквизиты: такого счёта не существует.",
        "kk": "Деректемелерді түзетіңіз: мұндай шот жоқ.",
        "en": "Fix the requisites: this account does not exist.",
    },
    "next_action.invalid_fields": {
        "ru": "Исправьте неверное поле ({fields}) и повторите проверку.",
        "kk": "Қате толтырылған өрісті түзетіңіз ({fields}) және тексеруді қайталаңыз.",
        "en": "Fix the invalid field ({fields}) and run the check again.",
    },
    "invalid_field.bin": {"ru": "БИН/ИИН", "kk": "БСН/ЖСН", "en": "BIN/IIN"},
    "invalid_field.iik": {"ru": "ИИК", "kk": "ЖСК (ИИК)", "en": "IIK"},
    "invalid_field.bik": {"ru": "БИК", "kk": "БСК (БИК)", "en": "BIK"},
    # --- HTTP & business error messages ---
    "error.internal": {
        "ru": "Внутренняя ошибка сервиса. Попробуйте повторить запрос позже.",
        "kk": "Сервистің ішкі қатесі. Сұрауды кейінірек қайталап көріңіз.",
        "en": "Internal service error. Please try again later.",
    },
    "error.unknown_payer": {
        "ru": "Неизвестный плательщик: {payer_id}.",
        "kk": "Белгісіз төлеуші: {payer_id}.",
        "en": "Unknown payer: {payer_id}.",
    },
    "error.approval_not_found": {
        "ru": "Заявка на согласование не найдена.",
        "kk": "Келісуге арналған өтінім табылмады.",
        "en": "Approval request not found.",
    },
    "error.approval_already_decided": {
        "ru": "Решение по этой заявке уже принято.",
        "kk": "Бұл өтінім бойынша шешім қабылданып қойған.",
        "en": "A decision has already been recorded for this approval request.",
    },
    "error.invalid_payment_cannot_approve": {
        "ru": "Платёж с ошибкой в реквизитах нельзя одобрить.",
        "kk": "Деректемелерінде қате бар төлемді келісуге болмайды.",
        "en": "A payment with invalid requisites cannot be approved.",
    },
    "error.trust_not_allowed": {
        "ru": "Доверие недоступно для этого платежа",
        "kk": "Бұл төлем үшін шотқа сенім білдіру мүмкін емес.",
        "en": "Account trust is not available for this payment.",
    },
    "error.trust_comment_required": {
        "ru": (
            "Для добавления счёта в доверенные обязателен комментарий директора "
            "(не менее 10 символов)."
        ),
        "kk": (
            "Шотты сенімділер тізіміне қосу үшін директордың түсініктемесі міндетті "
            "(кемінде 10 таңба)."
        ),
        "en": "A director comment of at least 10 characters is required to trust this account.",
    },
    "error.red_comment_required": {
        "ru": (
            "Для одобрения платежа с красным вердиктом обязателен комментарий директора "
            "(не менее 10 символов)."
        ),
        "kk": (
            "Қорытындысы «қызыл» төлемді келісу үшін директордың түсініктемесі міндетті "
            "(кемінде 10 таңба)."
        ),
        "en": "A director comment of at least 10 characters is required to approve a red-verdict payment.",
    },
    "error.metrics_missing": {
        "ru": "Оценочный набор не найден. Сгенерируйте data/eval_set.json.",
        "kk": "Бағалау жинағы табылмады. data/eval_set.json файлын жасаңыз.",
        "en": "Evaluation dataset not found. Generate data/eval_set.json first.",
    },
    "error.validation_fallback": {
        "ru": "Ошибка проверки данных запроса.",
        "kk": "Сұрау деректерін тексеру қатесі.",
        "en": "Request validation error.",
    },
    # --- Request validation messages (422) ---
    "val.json_invalid": {
        "ru": "Некорректный формат JSON в теле запроса.",
        "kk": "Сұрау мәтініндегі JSON пішімі дұрыс емес.",
        "en": "Invalid JSON format in request body.",
    },
    "val.missing": {
        "ru": "обязательное поле не заполнено.",
        "kk": "міндетті өріс толтырылмаған.",
        "en": "required field is missing.",
    },
    "val.greater_than": {
        "ru": "значение должно быть больше {gt}.",
        "kk": "мәні {gt} санынан үлкен болуы тиіс.",
        "en": "value must be greater than {gt}.",
    },
    "val.less_than_equal": {
        "ru": "значение не должно превышать {le}.",
        "kk": "мәні {le} санынан аспауы тиіс.",
        "en": "value must not exceed {le}.",
    },
    "val.finite_number": {
        "ru": "значение должно быть конечным числом (без NaN и бесконечности).",
        "kk": "мәні ақырлы сан болуы тиіс (NaN және шексіздікке жол берілмейді).",
        "en": "value must be a finite number (no NaN or infinity).",
    },
    "val.string_too_short": {
        "ru": "длина должна быть не менее {min_length} симв.",
        "kk": "ұзындығы кемінде {min_length} таңба болуы тиіс.",
        "en": "length must be at least {min_length} characters.",
    },
    "val.string_too_long": {
        "ru": "длина не должна превышать {max_length} симв.",
        "kk": "ұзындығы {max_length} таңбадан аспауы тиіс.",
        "en": "length must not exceed {max_length} characters.",
    },
    "val.number_invalid": {
        "ru": "укажите корректное число.",
        "kk": "жарамды сан көрсетіңіз.",
        "en": "please provide a valid number.",
    },
    "val.string_type": {
        "ru": "значение должно быть строкой.",
        "kk": "мәні мәтін болуы тиіс.",
        "en": "value must be a string.",
    },
    "val.bool_parsing": {
        "ru": "значение должно быть логическим (true/false).",
        "kk": "мәні логикалық (true/false) болуы тиіс.",
        "en": "value must be a boolean (true/false).",
    },
    "val.literal_error": {
        "ru": "недопустимое значение (ожидается: {expected}).",
        "kk": "жарамсыз мән (мүмкін мәндер: {expected}).",
        "en": "invalid value (expected: {expected}).",
    },
    "val.recipient_name_required": {
        "ru": "Укажите название получателя.",
        "kk": "Алушының атауын көрсетіңіз.",
        "en": "Please enter the recipient name.",
    },
    "val.amount_finite": {
        "ru": "Сумма платежа должна быть конечным числом.",
        "kk": "Төлем сомасы ақырлы сан болуы тиіс.",
        "en": "Payment amount must be a finite number.",
    },
    "val.value_error_fallback": {
        "ru": "Некорректное значение поля.",
        "kk": "Өріс мәні қате.",
        "en": "Invalid field value.",
    },
    "val.generic": {
        "ru": "некорректное значение.",
        "kk": "жарамсыз мән.",
        "en": "invalid value.",
    },
    # --- Localized Evidence labels & templates ---
    "ev.field.bin": {"ru": "БИН/ИИН", "kk": "БСН/ЖСН", "en": "BIN/IIN"},
    "ev.field.iik": {"ru": "ИИК", "kk": "ЖСК (ИИК)", "en": "IIK"},
    "ev.field.bik": {"ru": "БИК", "kk": "БСК (БИК)", "en": "BIK"},
    "ev.field.bank": {"ru": "Банк", "kk": "Банк", "en": "Bank"},
    "ev.field.name": {"ru": "Название", "kk": "Атауы", "en": "Name"},
    "ev.field.amount": {"ru": "Сумма", "kk": "Сома", "en": "Amount"},
    "ev.field.purpose": {"ru": "Назначение", "kk": "Төлем мақсаты", "en": "Purpose"},
    "ev.bin_expected": {
        "ru": "12 цифр с верной контрольной суммой",
        "kk": "бақылау сомасы дұрыс 12 цифр",
        "en": "12 digits with valid checksum",
    },
    "ev.iik_expected": {
        "ru": "20 символов формата KZ...",
        "kk": "KZ... пішіміндегі 20 таңба",
        "en": "20 characters in KZ... format",
    },
    "ev.bik_expected": {
        "ru": "8-символьный БИК банка РК",
        "kk": "ҚР банкінің 8 таңбалы БСК",
        "en": "8-character Kazakhstan bank BIK",
    },
    "ev.bank_code_bik": {
        "ru": "код {code} ({bik})",
        "kk": "{code} коды ({bik})",
        "en": "code {code} ({bik})",
    },
    "ev.bank_code_only": {
        "ru": "код {code}",
        "kk": "{code} коды",
        "en": "code {code}",
    },
    "ev.bcc_active_expected": {
        "ru": "действующий счёт в BCC",
        "kk": "BCC-дегі қолданыстағы шот",
        "en": "active BCC account",
    },
    "ev.bcc_owner_expected": {
        "ru": "совпадение владельца счёта с указанным получателем",
        "kk": "шот иесінің көрсетілген алушымен сәйкестігі",
        "en": "account owner matches specified recipient",
    },
    "ev.bcc_owner_mismatch": {
        "ru": "владелец счёта не совпадает с указанным получателем",
        "kk": "шот иесі көрсетілген алушымен сәйкес келмейді",
        "en": "account owner does not match specified recipient",
    },
    "ev.bcc_owner_verified": {
        "ru": "владелец счёта подтверждён банком",
        "kk": "шот иесі банкпен расталған",
        "en": "account owner verified by bank",
    },
    "ev.name_bin": {
        "ru": "{name} (БИН {bin})",
        "kk": "{name} (БСН {bin})",
        "en": "{name} (BIN {bin})",
    },
    "ev.single_script_expected": {
        "ru": "один алфавит в пределах слова",
        "kk": "бір сөз ішінде бір әліпби",
        "en": "single alphabet within a word",
    },
    "ev.mixed_script_actual": {
        "ru": "в названии есть символы другого алфавита или цифры вместо букв",
        "kk": "атауда басқа әліпби таңбалары немесе әріп орнына цифрлар бар",
        "en": "characters from another alphabet or digits used in place of letters",
    },
    "ev.account_for_bin": {
        "ru": "счёт для БИН {bin}",
        "kk": "БСН {bin} үшін шот",
        "en": "account for BIN {bin}",
    },
    "ev.used_for_other": {
        "ru": "использовался для {name} (БИН {bin})",
        "kk": "{name} (БСН {bin}) үшін қолданылған",
        "en": "used for {name} (BIN {bin})",
    },
    "ev.trusted_for_other": {
        "ru": "доверен для {name} (БИН {bin})",
        "kk": "{name} (БСН {bin}) үшін сенімді деп белгіленген",
        "en": "trusted for {name} (BIN {bin})",
    },
    "ev.legal_bin": {
        "ru": "БИН юрлица",
        "kk": "заңды тұлғаның БСН-і",
        "en": "legal entity BIN",
    },
    "ev.individual_iin": {
        "ru": "ИИН физлица",
        "kk": "жеке тұлғаның ЖСН-і",
        "en": "individual IIN",
    },
    "ev.kbe_17_expected": {
        "ru": "БИН юрлица (КБе 17)",
        "kk": "заңды тұлғаның БСН-і (КБе 17)",
        "en": "legal entity BIN (KBe 17)",
    },
    "ev.kbe_19_expected": {
        "ru": "ИИН физлица (КБе 19)",
        "kk": "жеке тұлғаның ЖСН-і (КБе 19)",
        "en": "individual IIN (KBe 19)",
    },
    "ev.knp_label": {
        "ru": "КНП {knp}",
        "kk": "КНП {knp}",
        "en": "KNP {knp}",
    },
    "ev.new_bcc_expected": {
        "ru": "действующий счёт получателя",
        "kk": "алушының қолданыстағы шоты",
        "en": "established recipient account",
    },
    "ev.new_bcc_actual": {
        "ru": "счёт открыт недавно",
        "kk": "шот жақында ашылған",
        "en": "account opened recently",
    },
    "ev.amount_p90_expected": {
        "ru": "не выше {amount} (p90 клиента)",
        "kk": "{amount} аспауы (клиенттің p90 мәні)",
        "en": "at most {amount} (client p90)",
    },
    "ev.amount_around": {
        "ru": "около {amount}",
        "kk": "шамамен {amount}",
        "en": "around {amount}",
    },
    "ev.first_payment_expected": {
        "ru": "предыдущие платежи в истории",
        "kk": "тарихтағы алдыңғы төлемдер",
        "en": "prior payments in history",
    },
    "ev.first_payment_actual": {
        "ru": "0 платежей",
        "kk": "0 төлем",
        "en": "0 payments",
    },
    "ev.bin_young_expected": {
        "ru": "регистрация компании от {months} месяцев",
        "kk": "компания кемінде {months} ай бұрын тіркелген",
        "en": "company registered at least {months} months ago",
    },
    "ev.bin_young_actual": {
        "ru": "зарегистрирована {reg_date} ({months} мес. назад)",
        "kk": "{reg_date} тіркелген ({months} ай бұрын)",
        "en": "registered {reg_date} ({months} mo. ago)",
    },
    "ev.urgent_expected": {
        "ru": "обычное назначение платежа",
        "kk": "әдеттегі төлем мақсаты",
        "en": "standard payment purpose",
    },
    "ev.trusted_default": {
        "ru": "Подтверждено директором",
        "kk": "Директор растаған",
        "en": "Confirmed by director",
    },
    "ev.duplicate_invoice_expected": {
        "ru": "уникальный номер счёта",
        "kk": "төлем шотының бірегей нөмірі",
        "en": "unique invoice number",
    },
    "ev.duplicate_invoice_actual": {
        "ru": "счёт № {invoice_no}",
        "kk": "№ {invoice_no} төлем шоты",
        "en": "invoice #{invoice_no}",
    },
    "ev.accum_expected_fallback": {
        "ru": "разовый платёж новому получателю",
        "kk": "жаңа алушыға бір реттік төлем",
        "en": "single payment to new recipient",
    },
    "ev.accum_actual": {
        "ru": "{total} за {days} дн. ({count} оп.)",
        "kk": "{days} күнде {total} ({count} оп.)",
        "en": "{total} over {days}d ({count} ops)",
    },
    "ev.structuring_actual": {
        "ru": "{total} за {hours} ч ({count} оп.)",
        "kk": "{hours} сағатта {total} ({count} оп.)",
        "en": "{total} over {hours}h ({count} ops)",
    },
    "ev.analyst_bcc_expected": {
        "ru": "счёт на БИН {bin}",
        "kk": "БСН {bin} бойынша рәсімделген шот",
        "en": "account for BIN {bin}",
    },
    "ev.analyst_bcc_actual": {
        "ru": "владелец {owner_name} (БИН {owner_bin})",
        "kk": "иесі {owner_name} (БСН {owner_bin})",
        "en": "owner {owner_name} (BIN {owner_bin})",
    },
    "ev.analyst_new_bcc_expected": {
        "ru": "счёт старше {days} дней",
        "kk": "шот {days} күннен бұрын ашылған",
        "en": "account older than {days} days",
    },
    "ev.analyst_new_bcc_actual": {
        "ru": "открыт {age_days} дн. назад ({opened_at})",
        "kk": "{age_days} күн бұрын ашылған ({opened_at})",
        "en": "opened {age_days}d ago ({opened_at})",
    },
    "ev.bank_complaints_expected": {
        "ru": "нет жалоб от других клиентов банка",
        "kk": "банктің басқа клиенттерінен шағым жоқ",
        "en": "no reports from other bank clients",
    },
    "ev.bank_complaints_actual_some": {
        "ru": "поступали жалобы от других клиентов банка",
        "kk": "банктің басқа клиенттерінен шағымдар түскен",
        "en": "reported by other bank clients",
    },
    "ev.bank_complaints_actual_many": {
        "ru": "несколько (3+) жалоб от других клиентов банка",
        "kk": "банктің басқа клиенттерінен бірнеше (3+) шағым",
        "en": "multiple (3+) reports from other bank clients",
    },
    "ev.analyst_complaints_actual": {
        "ru": "жалоб: {count} (последняя: {last_reported_at})",
        "kk": "шағымдар: {count} (соңғысы: {last_reported_at})",
        "en": "{count} report(s) (latest: {last_reported_at})",
    },
    "ev.watchlist_expected": {
        "ru": "счёт отсутствует в списке подозрительных счетов",
        "kk": "шот күдікті шоттар тізімінде жоқ",
        "en": "account not on suspicious account watchlist",
    },
    "ev.watchlist_actual": {
        "ru": "счёт в стоп-листе антифрод-центра",
        "kk": "шот антифрод-орталықтың стоп-тізімінде",
        "en": "account on antifraud center watchlist",
    },
    "ev.analyst_watchlist_actual": {
        "ru": "{source} ({category}, {added_at})",
        "kk": "{source} ({category}, {added_at})",
        "en": "{source} ({category}, {added_at})",
    },
    "ev.fresh_inflows_expected": {
        "ru": "обычная активность новых входящих платежей",
        "kk": "жаңа кіріс төлемдерінің әдеттегі белсенділігі",
        "en": "normal pattern of incoming first-time payments",
    },
    "ev.fresh_inflows_actual_medium": {
        "ru": "первые платежи от нескольких (3+) не связанных компаний",
        "kk": "өзара байланысы жоқ бірнеше (3+) компаниядан алғашқы төлемдер",
        "en": "first-time payments from several (3+) unrelated companies",
    },
    "ev.fresh_inflows_actual_high": {
        "ru": "первые платежи от многих (5+) не связанных компаний",
        "kk": "өзара байланысы жоқ көптеген (5+) компаниядан алғашқы төлемдер",
        "en": "first-time payments from many (5+) unrelated companies",
    },
    "ev.analyst_fresh_inflows_expected": {
        "ru": "менее {threshold} новых не связанных плательщиков за {window_days} дн.",
        "kk": "{window_days} күнде өзара байланысы жоқ {threshold}-тен аз жаңа төлеуші",
        "en": "fewer than {threshold} unrelated first-time payers in {window_days}d",
    },
    "ev.analyst_fresh_inflows_actual": {
        "ru": "{distinct_payers} не связанных клиентов, {total_kzt} за {window_days} дн.",
        "kk": "өзара байланысы жоқ {distinct_payers} клиент, {window_days} күнде {total_kzt}",
        "en": "{distinct_payers} unrelated clients, {total_kzt} over {window_days}d",
    },
    # --- Evaluation disclaimers ---
    "metrics.disclaimer": {
        "ru": (
            "Честное предупреждение: оценочный набор синтетический и сгенерирован той же командой, "
            "которая разрабатывала правила проверки, на основе синтетической истории одного клиента. "
            "Метрики показывают поведение движка на заданных сценариях, не отражают реальную "
            "банковскую статистику мошенничества и не заменяют проверку на исторических боевых данных. "
            "Известные слепые зоны (новый дроп в стороннем банке до первых жалоб и притока, умеренное "
            "завышение суммы без смены реквизитов, ИИН-дроп без ОПФ/КБе и первая неподтверждённая "
            "смена счёта) намеренно сохранены в наборе без подгонки детектора."
        ),
        "kk": (
            "Ашық ескерту: бағалау жинағы синтетикалық, ол тексеру ережелерін әзірлеген сол топпен "
            "бір клиенттің синтетикалық төлем тарихы негізінде жасалған. Көрсеткіштер тексеру жүйесінің "
            "үлгіленген сценарийлердегі жұмысын бейнелейді, нақты банктік алаяқтық статистикасын "
            "көрсетпейді және нақты тарихи өндірістік деректерде тексеруді алмастырмайды. Белгілі соқыр аймақтар "
            "(алғашқы шағымдар мен ағынға дейінгі сыртқы банктегі жаңа дроп, деректемелерді өзгертпей соманы "
            "орташа арттыру, ҰҚН/КБе жоқ ЖСН-дроп және алғашқы расталмаған шот ауыстыру) жинақта детекторды "
            "бейімдемей, әдейі сақталған."
        ),
        "en": (
            "Synthetic evaluation notice: this dataset is synthetic and generated by the same team "
            "that wrote the verification rules, based on one client's synthetic payment history. "
            "Metrics illustrate engine behavior on modeled scenarios, do not represent real banking "
            "fraud incidence, and do not replace validation on production payment logs. Known blind "
            "spots (brand-new external drops prior to complaints or multi-client inflows, moderate "
            "amount inflation without requisite changes, IIN droppers without legal form/KBe, and first "
            "unconfirmed account switches) are intentionally preserved without tuning the detector to the set."
        ),
    },
    # --- Prod API error messages (error.prod.*) ---
    "error.prod.not_authenticated": {
        "ru": "Требуется вход в систему.",
        "kk": "Жүйеге кіру қажет.",
        "en": "Authentication required.",
    },
    "error.prod.invalid_credentials": {
        "ru": "Неверный логин или пароль.",
        "kk": "Логин немесе құпиясөз қате.",
        "en": "Invalid login or password.",
    },
    "error.prod.forbidden_role": {
        "ru": "Недостаточно прав для выполнения этого действия.",
        "kk": "Бұл әрекетті орындау үшін құқықтар жеткіліксіз.",
        "en": "You do not have permission to perform this action.",
    },
    "error.prod.csrf_header_missing": {
        "ru": "Отсутствует обязательный заголовок безопасности запроса.",
        "kk": "Сұраудың міндетті қауіпсіздік тақырыбы жоқ.",
        "en": "Missing required security request header.",
    },
    "error.prod.not_found": {
        "ru": "Запрошенный ресурс не найден.",
        "kk": "Сұралған ресурс табылмады.",
        "en": "Requested resource not found.",
    },
    "error.prod.already_signed": {
        "ru": "Платёж уже подписан.",
        "kk": "Бұл төлемге қол қойылып қойған.",
        "en": "This payment has already been signed.",
    },
    "error.prod.not_signable_status": {
        "ru": "Платёж в текущем статусе нельзя подписать.",
        "kk": "Ағымдағы күйдегі төлемге қол қоюға болмайды.",
        "en": "Payment cannot be signed in its current status.",
    },
    "error.prod.approval_pending": {
        "ru": "Платёж ожидает решения директора.",
        "kk": "Төлем директордың шешімін күтуде.",
        "en": "Payment is awaiting director approval.",
    },
    "error.prod.approval_rejected": {
        "ru": "Платёж отклонён директором. Измените реквизиты или отмените платёж.",
        "kk": "Төлемді директор қабылдамады. Деректемелерді түзетіңіз немесе төлемді болдырмаңыз.",
        "en": "Payment was rejected by the director. Edit the requisites or cancel the payment.",
    },
    "error.prod.verdict_changed": {
        "ru": "При перепроверке уровень риска повысился — проверьте обновлённый разбор.",
        "kk": "Қайта тексеру кезінде тәуекел деңгейі өсті — жаңартылған нәтижені тексеріңіз.",
        "en": "Risk verdict worsened upon recheck — review the updated check result.",
    },
    "error.prod.invalid_requisites": {
        "ru": "В реквизитах платежа есть ошибка — исправьте их перед отправкой или подписанием.",
        "kk": "Төлем деректемелерінде қате бар — жіберу немесе қол қою алдында түзетіңіз.",
        "en": "Payment requisites are invalid — fix them before sending or signing.",
    },
    "error.prod.red_requires_approval": {
        "ru": "Платёж с красным вердиктом нельзя подписать без одобрения директора.",
        "kk": "Қызыл деңгейлі төлемге директордың мақұлдауынсыз қол қоюға болмайды.",
        "en": "A red-verdict payment cannot be signed without director approval.",
    },
    "error.prod.ack_or_approval_required": {
        "ru": "Для подписи требуется подтверждение бухгалтера или одобрение директора.",
        "kk": "Қол қою үшін бухгалтердің растауы немесе директордың мақұлдауы қажет.",
        "en": "Accountant acknowledgement or director approval is required to sign.",
    },
    "error.prod.not_editable": {
        "ru": "Платёж в текущем статусе нельзя редактировать или перепроверять.",
        "kk": "Ағымдағы күйдегі төлемді өңдеуге немесе қайта тексеруге болмайды.",
        "en": "Payment cannot be edited or rechecked in its current status.",
    },
    "error.prod.invalid_transition": {
        "ru": "Недопустимый переход статуса для этого платежа.",
        "kk": "Бұл төлем үшін күйді осылай ауыстыруға болмайды.",
        "en": "Invalid status transition for this payment.",
    },
    "error.prod.approval_already_decided": {
        "ru": "Решение по этой заявке уже принято.",
        "kk": "Бұл өтінім бойынша шешім қабылданып қойған.",
        "en": "A decision has already been recorded for this approval request.",
    },
    "error.prod.approval_superseded": {
        "ru": "Согласование устарело из-за изменения реквизитов или вердикта.",
        "kk": "Деректемелер немесе вердикт өзгергендіктен келісу ескірді.",
        "en": "Approval has been superseded due to changed requisites or verdict.",
    },
    "error.prod.duplicate_file": {
        "ru": "Этот файл уже загружался ранее. Подтвердите повторную загрузку.",
        "kk": "Бұл файл бұрын жүктелген. Қайта жүктеуді растаңыз.",
        "en": "This file has already been imported. Confirm repeat upload to continue.",
    },
    "error.prod.file_too_large": {
        "ru": "Размер файла превышает допустимый лимит (2 МБ).",
        "kk": "Файл көлемі рұқсат етілген шектен (2 МБ) асады.",
        "en": "File size exceeds the maximum allowed limit (2 MB).",
    },
    "error.prod.validation_error": {
        "ru": "Ошибка проверки данных запроса.",
        "kk": "Сұрау деректерін тексеру қатесі.",
        "en": "Request validation error.",
    },
    "error.prod.unsupported_file": {
        "ru": "Не удалось распознать формат файла. Загрузите выгрузку 1С или CSV.",
        "kk": "Файл пішімін тану мүмкін болмады. 1С немесе CSV файлын жүктеңіз.",
        "en": "Unsupported or unrecognized file format. Upload a 1C exchange or CSV file.",
    },
    "error.prod.empty_file": {
        "ru": "Файл пуст и не содержит платёжных документов.",
        "kk": "Файл бос және төлем құжаттарын қамтымайды.",
        "en": "File is empty and contains no payment documents.",
    },
    "error.prod.red_comment_required": {
        "ru": (
            "Для одобрения платежа с красным вердиктом обязателен комментарий директора "
            "(не менее 10 символов)."
        ),
        "kk": (
            "Қызыл деңгейлі төлемді мақұлдау үшін директордың түсініктемесі міндетті "
            "(кемінде 10 таңба)."
        ),
        "en": "A director comment of at least 10 characters is required to approve a red-verdict payment.",
    },
    "error.prod.trust_comment_required": {
        "ru": (
            "Для добавления счёта в доверенные обязателен комментарий директора "
            "(не менее 10 символов)."
        ),
        "kk": (
            "Шотты сенімділер тізіміне қосу үшін директордың түсініктемесі міндетті "
            "(кемінде 10 таңба)."
        ),
        "en": "A director comment of at least 10 characters is required to trust this account.",
    },
    "error.prod.trust_not_allowed": {
        "ru": "Доверие недоступно для этого платежа.",
        "kk": "Бұл төлем үшін шотқа сенім білдіру қолжетімсіз.",
        "en": "Account trust is not available for this payment.",
    },
    "error.prod.invalid_payment_cannot_approve": {
        "ru": "Платёж с ошибкой в реквизитах нельзя одобрить.",
        "kk": "Деректемелерінде қате бар төлемді мақұлдауға болмайды.",
        "en": "A payment with invalid requisites cannot be approved.",
    },
    "error.prod.too_many_attempts": {
        "ru": "Слишком много неудачных попыток входа. Повторите через 15 минут.",
        "kk": "Кіру әрекеттері тым көп сәтсіз аяқталды. 15 минуттан кейін қайталаңыз.",
        "en": "Too many failed login attempts. Please try again in 15 minutes.",
    },
    "error.prod.internal_error": {
        "ru": "Внутренняя ошибка сервиса. Попробуйте повторить запрос позже.",
        "kk": "Сервистің ішкі қатесі. Сұрауды кейінірек қайталап көріңіз.",
        "en": "Internal service error. Please try again later.",
    },
    "error.prod.invalid_current_password": {
        "ru": "Текущий пароль указан неверно.",
        "kk": "Ағымдағы құпиясөз қате енгізілді.",
        "en": "The current password is incorrect.",
    },
    "error.prod.password_same_as_current": {
        "ru": "Новый пароль должен отличаться от текущего.",
        "kk": "Жаңа құпиясөз ағымдағы құпиясөзден өзгеше болуы тиіс.",
        "en": "The new password must differ from the current password.",
    },
    "error.prod.login_already_exists": {
        "ru": "Пользователь с таким логином уже существует.",
        "kk": "Мұндай логині бар пайдаланушы жүйеде бұрыннан бар.",
        "en": "A user with this login already exists.",
    },
    "error.prod.last_director_protected": {
        "ru": "Нельзя понизить или отключить единственного активного директора компании.",
        "kk": "Компанияның жалғыз белсенді директорының рөлін төмендетуге немесе оны өшіруге болмайды.",
        "en": "Cannot demote or deactivate the last active director of the company.",
    },
    "error.prod.threshold_requires_approval": {
        "ru": "Сумма платежа достигла порога согласования компании — требуется одобрение директора.",
        "kk": "Төлем сомасы компанияның келісу шегіне жетті — директордың мақұлдауы қажет.",
        "en": "Payment amount meets or exceeds the company approval threshold — director approval is required.",
    },
    "error.prod.invalid_date_range": {
        "ru": "Некорректный диапазон дат: дата начала не может быть позже даты окончания.",
        "kk": "Күндер аралығы қате: басталу күні аяқталу күнінен кейін болмауы тиіс.",
        "en": "Invalid date range: start date cannot be later than end date.",
    },
    "error.prod.pdf_unavailable": {
        "ru": "Экспорт в PDF сейчас недоступен.",
        "kk": "PDF пішіміне экспорттау қазір қолжетімсіз.",
        "en": "PDF export is currently unavailable.",
    },
    # --- Prod notification templates ---
    "prod.notif.approval_pending.title": {
        "ru": "Заявка на согласование",
        "kk": "Келісуге өтінім түсті",
        "en": "Approval requested",
    },
    "prod.notif.approval_pending.body": {
        "ru": "{recipient} · {amount} — отправлено на согласование ({verdict}).",
        "kk": "{recipient} · {amount} — төлем шоты келісуге жіберілді ({verdict}).",
        "en": "{recipient} · {amount} — submitted for approval ({verdict}).",
    },
    "prod.notif.approval_approved.title": {
        "ru": "Платёж одобрен директором",
        "kk": "Төлемді директор мақұлдады",
        "en": "Payment approved by director",
    },
    "prod.notif.approval_approved.body": {
        "ru": "{recipient} · {amount} — можно подписывать.",
        "kk": "{recipient} · {amount} — төлем шотына қол қоюға болады.",
        "en": "{recipient} · {amount} — ready to sign.",
    },
    "prod.notif.approval_rejected.title": {
        "ru": "Платёж отклонён директором",
        "kk": "Төлемді директор қабылдамады",
        "en": "Payment rejected by director",
    },
    "prod.notif.approval_rejected.body": {
        "ru": "{recipient} · {amount} — требуется исправление реквизитов или отмена.",
        "kk": "{recipient} · {amount} — деректемелерді түзету немесе төлемнен бас тарту қажет.",
        "en": "{recipient} · {amount} — edit requisites or cancel the payment.",
    },
    "prod.notif.sign_denied.title": {
        "ru": "Подпись заблокирована сервером",
        "kk": "Қол қою сервермен бұғатталды",
        "en": "Signing blocked by server",
    },
    "prod.notif.sign_denied.body": {
        "ru": "{recipient} · {amount} — {reason}",
        "kk": "{recipient} · {amount} — {reason}",
        "en": "{recipient} · {amount} — {reason}",
    },
    # --- Prod export labels ---
    "prod.export.pdf_title": {
        "ru": "Что проверить перед подписью",
        "kk": "Қол қояр алдында нені тексеру керек",
        "en": "What to Check Before Signing",
    },
    "prod.export.pdf_subtitle": {
        "ru": "Отчёт проверки платёжных поручений · BCC Business Shield",
        "kk": "Төлем шоттарын тексеру есебі · BCC Business Shield",
        "en": "Payment Verification Report · BCC Business Shield",
    },
    "prod.export.company": {"ru": "Компания", "kk": "Компания", "en": "Company"},
    "prod.export.generated": {"ru": "Сформировано", "kk": "Қалыптастырылды", "en": "Generated"},
    "prod.export.scope": {"ru": "Выборка", "kk": "Іріктеме", "en": "Scope"},
    "prod.export.period": {"ru": "Период", "kk": "Кезең", "en": "Period"},
    "prod.export.total": {"ru": "Платежей", "kk": "Төлемдер саны", "en": "Payments"},
    "prod.export.empty": {
        "ru": "По заданным параметрам платежи не найдены.",
        "kk": "Көрсетілген параметрлер бойынша төлемдер табылмады.",
        "en": "No payments found for the selected filters.",
    },
    "prod.export.reasons": {"ru": "Причины и сигналы", "kk": "Себептер мен белгілер", "en": "Reasons & signals"},
    "prod.export.no_signals": {
        "ru": "Замечаний не выявлено.",
        "kk": "Ескертулер анықталған жоқ.",
        "en": "No risk signals detected.",
    },
    "prod.export.advice": {"ru": "Рекомендация", "kk": "Ұсыным", "en": "Advice"},
    "prod.export.purpose": {"ru": "Назначение", "kk": "Төлем мақсаты", "en": "Purpose"},
    "prod.export.approval": {"ru": "Согласование", "kk": "Келісу", "en": "Approval"},
    "prod.export.page": {"ru": "Стр. {page} из {pages}", "kk": "{page} / {pages}-бет", "en": "Page {page} of {pages}"},
    "prod.verdict.green": {"ru": "Зелёный", "kk": "Жасыл", "en": "Green"},
    "prod.verdict.yellow": {"ru": "Жёлтый", "kk": "Сары", "en": "Yellow"},
    "prod.verdict.red": {"ru": "Красный", "kk": "Қызыл", "en": "Red"},
    "prod.verdict.grey": {"ru": "Серый", "kk": "Сұр", "en": "Grey"},
    "prod.verdict.invalid": {"ru": "Ошибка реквизитов", "kk": "Деректеме қатесі", "en": "Invalid"},
    "prod.status.checked": {"ru": "Проверен", "kk": "Тексерілді", "en": "Checked"},
    "prod.status.pending_approval": {"ru": "У директора", "kk": "Директорда", "en": "With director"},
    "prod.status.approved": {"ru": "Одобрен", "kk": "Мақұлданды", "en": "Approved"},
    "prod.status.rejected": {"ru": "Отклонён", "kk": "Қабылданбады", "en": "Rejected"},
    "prod.status.postponed": {"ru": "Отложен", "kk": "Кейінге қалдырылды", "en": "Postponed"},
    "prod.status.signed": {"ru": "Подписан", "kk": "Қол қойылды", "en": "Signed"},
    "prod.status.cancelled": {"ru": "Отменён", "kk": "Бас тартылды", "en": "Cancelled"},
}

KIND_LABELS: dict[str, dict[Lang, str]] = {
    "legit_same": {
        "ru": "Повторный платёж постоянному поставщику",
        "kk": "Тұрақты жеткізушіге қайталанатын төлем",
        "en": "Repeat payment to known supplier",
    },
    "legit_name_formatting_variant": {
        "ru": "Вариант написания ОПФ/кавычек",
        "kk": "ҰҚН (ОПФ) және тырнақша жазылу нұсқасы",
        "en": "Legal-form / formatting name variant",
    },
    "legit_seasonal_amount": {
        "ru": "Сезонный или крупный легитимный платёж",
        "kk": "Маусымдық немесе ірі заңды төлем",
        "en": "Seasonal or bulk legitimate payment",
    },
    "legit_account_change_confirmed": {
        "ru": "Подтверждённая смена счёта",
        "kk": "Расталған шот ауыстыру",
        "en": "Confirmed supplier account switch",
    },
    "legit_account_change_unconfirmed": {
        "ru": "Первая неподтверждённая смена счёта",
        "kk": "Алғашқы расталмаған шот ауыстыру",
        "en": "First unconfirmed account switch",
    },
    "legit_new_supplier": {
        "ru": "Новый легитимный поставщик",
        "kk": "Жаңа заңды жеткізуші",
        "en": "New legitimate supplier",
    },
    "legit_rebrand_same_account": {
        "ru": "Смена названия при том же счёте",
        "kk": "Шотты сақтап, атауды ауыстыру",
        "en": "Supplier rebrand on same account",
    },
    "legit_urgent_known_supplier": {
        "ru": "Срочный платёж постоянному поставщику",
        "kk": "Тұрақты жеткізушіге шұғыл төлем",
        "en": "Urgent payment to known supplier",
    },
    "legit_budget_payment": {
        "ru": "Бюджетный платёж (казначейство / ГК)",
        "kk": "Бюджеттік төлем (қазынашылық / МК)",
        "en": "Budget payment (treasury / gov)",
    },
    "legit_popular_known_supplier": {
        "ru": "Крупный известный банку поставщик (много первых платежей)",
        "kk": "Банкке бұрыннан белгілі ірі жеткізуші (көп алғашқы төлем)",
        "en": "Established bank-known supplier (high first-payment inflow)",
    },
    "legit_new_supplier_generic_word": {
        "ru": "Новый легитимный поставщик с общим словом в названии",
        "kk": "Атауында жалпы сөз бар жаңа заңды жеткізуші",
        "en": "New legitimate supplier with a generic word",
    },
    "attack_iik_swap_same_bin": {
        "ru": "Подмена ИИК при том же БИН",
        "kk": "Сол БСН кезінде ЖСК-ны алмастыру",
        "en": "IIK swap under same supplier BIN",
    },
    "attack_lookalike_name": {
        "ru": "Двойник названия поставщика (другой БИН)",
        "kk": "Жеткізуші атауына ұқсас атау (басқа БСН)",
        "en": "Lookalike supplier name (different BIN)",
    },
    "attack_unicode_and_digit_evasion": {
        "ru": "Обход через Unicode, confusables и цифры",
        "kk": "Unicode, ұқсас таңбалар және цифрлар арқылы айналып өту",
        "en": "Unicode, confusables, and digit-for-letter evasion",
    },
    "attack_bcc_other_owner": {
        "ru": "Счёт BCC оформлен на другую компанию",
        "kk": "BCC шоты басқа компанияға рәсімделген",
        "en": "BCC account owned by another company",
    },
    "attack_iin_dropper": {
        "ru": "Перевод на ИИН физлица (дроппер / КБе 17)",
        "kk": "Жеке тұлғаның ЖСН-іне аударым (дроппер / КБе 17)",
        "en": "Individual IIN dropper (OPF / KBe 17 mismatch)",
    },
    "attack_amount_inflation": {
        "ru": "Завышение суммы платежа",
        "kk": "Төлем сомасын шектен тыс арттыру",
        "en": "Payment amount inflation",
    },
    "attack_iik_reused_other_supplier": {
        "ru": "Чужой ИИК из истории другого поставщика",
        "kk": "Басқа жеткізушінің тарихынан алынған ЖСК",
        "en": "IIK reused from another supplier",
    },
    "attack_duplicate_invoice": {
        "ru": "Повторная оплата по дубликату счёта",
        "kk": "Төлем шотының телнұсқасы бойынша қайта төлеу",
        "en": "Duplicate invoice payment",
    },
    "attack_structuring_72h": {
        "ru": "Дробление платежа (структурирование за 72 ч)",
        "kk": "Төлемді бөлшектеу (72 сағат ішінде)",
        "en": "Payment structuring / splitting within 72h",
    },
    "attack_typo_free_valid_drop": {
        "ru": "Чистая подставная компания без истории",
        "kk": "Тарихы жоқ таза жалған компания",
        "en": "Typo-free valid drop company without history",
    },
    "attack_combined_bec": {
        "ru": "Комбинированная BEC-атака",
        "kk": "Кешенді BEC-шабуыл",
        "en": "Combined multi-signal BEC attack",
    },
    "attack_bankwide_external_drop": {
        "ru": "Дроппер в стороннем банке (межклиентские сигналы BCC)",
        "kk": "Сыртқы банктегі дроппер (BCC клиенттері бойынша ортақ сигналдар)",
        "en": "External-bank dropper (bank-wide BCC signals)",
    },
}

FIELD_LABELS: dict[str, dict[Lang, str]] = {
    "payer_id": {"ru": "Плательщик", "kk": "Төлеуші", "en": "Payer"},
    "recipient_name": {"ru": "Название получателя", "kk": "Алушының атауы", "en": "Recipient name"},
    "recipient_bin": {
        "ru": "БИН/ИИН получателя",
        "kk": "Алушының БСН/ЖСН",
        "en": "Recipient BIN/IIN",
    },
    "recipient_iik": {"ru": "ИИК получателя", "kk": "Алушының ЖСК", "en": "Recipient IIK"},
    "recipient_bik": {"ru": "БИК банка", "kk": "Банктің БСК", "en": "Bank BIK"},
    "amount_kzt": {"ru": "Сумма платежа", "kk": "Төлем сомасы", "en": "Payment amount"},
    "purpose": {"ru": "Назначение платежа", "kk": "Төлем мақсаты", "en": "Payment purpose"},
    "kbe": {"ru": "КБе", "kk": "КБе", "en": "KBe"},
    "knp": {"ru": "КНП", "kk": "КНП", "en": "KNP"},
    "accountant_note": {
        "ru": "Комментарий бухгалтера",
        "kk": "Бухгалтердің түсініктемесі",
        "en": "Accountant note",
    },
    "director_comment": {
        "ru": "Комментарий директора",
        "kk": "Директордың түсініктемесі",
        "en": "Director comment",
    },
    "decision": {"ru": "Решение директора", "kk": "Директордың шешімі", "en": "Director decision"},
    "trust_account": {"ru": "Доверие счёту", "kk": "Шотқа сенім", "en": "Trust account"},
    "check_request": {"ru": "Данные платежа", "kk": "Төлем деректері", "en": "Payment details"},
    "lang": {"ru": "Язык ответа", "kk": "Жауап тілі", "en": "Response language"},
    "limit": {"ru": "Лимит записей", "kk": "Жазбалар лимиті", "en": "Record limit"},
    "login": {"ru": "Логин", "kk": "Логин", "en": "Login"},
    "password": {"ru": "Пароль", "kk": "Құпиясөз", "en": "Password"},
    "doc_number": {"ru": "Номер документа", "kk": "Құжат нөмірі", "en": "Document number"},
    "doc_date": {"ru": "Дата документа", "kk": "Құжат күні", "en": "Document date"},
    "note": {"ru": "Комментарий", "kk": "Түсініктеме", "en": "Note"},
    "comment": {"ru": "Комментарий", "kk": "Түсініктеме", "en": "Comment"},
    "accountant_ack": {
        "ru": "Подтверждение бухгалтера",
        "kk": "Бухгалтердің растауы",
        "en": "Accountant acknowledgement",
    },
    "filename": {"ru": "Имя файла", "kk": "Файл атауы", "en": "Filename"},
    "full_name": {"ru": "Имя и фамилия", "kk": "Аты-жөні", "en": "Full name"},
    "default_lang": {"ru": "Язык интерфейса", "kk": "Интерфейс тілі", "en": "Default language"},
    "current_password": {"ru": "Текущий пароль", "kk": "Ағымдағы құпиясөз", "en": "Current password"},
    "new_password": {"ru": "Новый пароль", "kk": "Жаңа құпиясөз", "en": "New password"},
    "role": {"ru": "Роль", "kk": "Рөл", "en": "Role"},
    "is_active": {"ru": "Статус активности", "kk": "Белсенділік күйі", "en": "Active status"},
    "active": {"ru": "Статус активности", "kk": "Белсенділік күйі", "en": "Active status"},
    "notify_on": {"ru": "Режим уведомлений", "kk": "Хабарлама режимі", "en": "Notification filter"},
    "approval_threshold_kzt": {
        "ru": "Порог согласования (₸)",
        "kk": "Келісу шегі (₸)",
        "en": "Approval threshold (KZT)",
    },
    "from": {"ru": "Дата начала", "kk": "Басталу күні", "en": "Start date"},
    "to": {"ru": "Дата окончания", "kk": "Аяқталу күні", "en": "End date"},
    "format": {"ru": "Формат экспорта", "kk": "Экспорт пішімі", "en": "Export format"},
}


def kind_label(kind: str, lang: Lang = DEFAULT_LANG) -> str:
    """Return a human-readable localized label for an evaluation scenario kind."""
    entry = KIND_LABELS.get(kind)
    if entry is None:
        return kind
    return entry[lang]


def resolve_lang(raw: str | None) -> Lang:
    """Return raw if it is a supported language code, otherwise fall back to DEFAULT_LANG."""
    if raw == "kk":
        return "kk"
    if raw == "en":
        return "en"
    return DEFAULT_LANG


def t(key: str, lang: Lang = DEFAULT_LANG, **params: Any) -> str:
    """Render a localized message template by key and language."""
    template = MESSAGES[key][lang]
    return template.format(**params) if params else template


def field_label(field_key: str, lang: Lang = DEFAULT_LANG) -> str:
    """Return a localized label for an API request field."""
    entry = FIELD_LABELS.get(field_key)
    if entry is None:
        return field_key
    return entry[lang]
