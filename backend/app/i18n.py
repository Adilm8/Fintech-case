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
        "kk": "ЖСК-да латын әріптерінің орнына кириллица табылды — пернетақта тілін тексеріңіз.",
        "en": "The IIK contains Cyrillic letters instead of Latin ones — check your keyboard layout.",
    },
    "iik.length": {
        "ru": "ИИК должен состоять из 20 символов (сейчас {length}).",
        "kk": "ЖСК 20 таңбадан тұруы тиіс (қазір {length}).",
        "en": "The IIK must be 20 characters long (currently {length}).",
    },
    "iik.uppercase": {
        "ru": "ИИК должен быть записан только заглавными латинскими буквами и цифрами.",
        "kk": "ЖСК тек бас латын әріптері мен цифрлардан тұруы тиіс.",
        "en": "The IIK must contain only uppercase Latin letters and digits.",
    },
    "iik.prefix_kz": {
        "ru": "ИИК казахстанского счёта должен начинаться с KZ.",
        "kk": "Қазақстандық шоттың ЖСК нөмірі KZ таңбаларынан басталуы тиіс.",
        "en": "A Kazakhstan account IIK must start with KZ.",
    },
    "iik.alnum": {
        "ru": "ИИК должен содержать только заглавные латинские буквы и цифры без пробелов.",
        "kk": "ЖСК бос орынсыз тек бас латын әріптері мен цифрлардан тұруы тиіс.",
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
        "kk": "ЖСК-да банк коды қате — 5–7-таңбалар цифр болуы тиіс.",
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
        "kk": "Шот нөміріндегі банк коды көрсетілген БСК (БИК) кодымен сәйкес келмейді.",
        "en": "The bank code in the account number does not match the specified BIK.",
    },
    # --- Risk scoring rule messages ---
    "rule.bcc_account_other_owner": {
        "ru": (
            "Этот счёт в БЦК оформлен на другую компанию ({owner_name}), "
            "а не на указанного получателя."
        ),
        "kk": (
            "БЦК-дағы бұл шот көрсетілген алушыға емес, "
            "басқа компанияға ({owner_name}) рәсімделген."
        ),
        "en": (
            "This BCC account is registered to another company ({owner_name}), "
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
    "rule.mixed_script_name": {
        "ru": "В названии получателя внутри кириллического слова подставлены буквы другого алфавита.",
        "kk": "Алушының атауындағы кириллица сөзінің ішінде басқа әліпби әріптері қолданылған.",  # review-kk
        "en": "The recipient name mixes letters from another alphabet inside a Cyrillic word.",
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
        "kk": "Бұл жеткізушіде сіз бұрын төлем жасамаған жаңа шот нөмірі көрсетілген.",
        "en": "This supplier has a new account number that you have not paid before.",
    },
    "rule.bank_changed": {
        "ru": "Сменился банк поставщика: раньше платежи шли в {old_bank}, а теперь в {new_bank}.",
        "kk": (
            "Жеткізушінің банкі ауысқан: бұрын төлемдер {old_bank} банкіне жіберілсе, "
            "қазір {new_bank} банкіне бағытталған."
        ),  # review-kk
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
    "rule.new_bcc_account": {
        "ru": "Счёт в БЦК открыт совсем недавно — {age_days} дн. назад.",
        "kk": "БЦК-дағы шот жақында ғана ашылған — {age_days} күн бұрын.",
        "en": "This BCC account was opened very recently — {age_days} days ago.",
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
            "Төлем мақсатында шұғылдық немесе деректемелердің ауысуы туралы сөздер бар — "
            "бұл шотты ауыстырудың жиі белгісі."
        ),  # review-kk
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
        "kk": "Шот директормен расталған",
        "en": "Account confirmed by director",
    },
    "headline.yellow": {
        "ru": "Есть изменения",
        "kk": "Өзгерістер бар",
        "en": "Changes detected",
    },
    "headline.red": {
        "ru": "Похоже на подмену",
        "kk": "Деректемелер ауыстырылғанға ұқсайды",  # review-kk
        "en": "Likely requisite substitution",
    },
    "headline.grey": {
        "ru": "Нет истории для сравнения",
        "kk": "Салыстыру үшін тарих жоқ",
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
    "next_action.yellow": {
        "ru": (
            "Позвоните поставщику по номеру из договора, "
            "а не из письма с новыми реквизитами, и подтвердите счёт."
        ),
        "kk": (
            "Жаңа деректемелер келген хаттағы емес, шарттағы нөмір бойынша "
            "жеткізушіге хабарласып, шотты растаңыз."
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
            "шарттағы нөмір бойынша жеткізушіге хабарласыңыз."
        ),
        "en": (
            "Do not sign this payment. Call the supplier using the phone number from your contract, "
            "not the email with new details."
        ),
    },
    "next_action.grey": {
        "ru": "Проверьте БИН поставщика в реестре и подтвердите реквизиты по телефону из договора.",
        "kk": "Жеткізушінің БСН-ін тізілімнен тексеріп, деректемелерді шарттағы телефон арқылы растаңыз.",
        "en": "Verify the supplier's BIN in the registry and confirm requisites by the phone number from your contract.",
    },
    "next_action.grey_above_p90": {
        "ru": (
            "Крупный первый платёж новому поставщику: проверьте БИН в реестре, "
            "подтвердите реквизиты по телефону из договора и согласуйте с директором."
        ),
        "kk": (
            "Жаңа жеткізушіге ірі алғашқы төлем: БСН-ді тізілімнен тексеріп, "
            "деректемелерді шарттағы телефон арқылы растап, директормен келісіңіз."
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
        "kk": "Деректемелерінде қате бар төлемді мақұлдауға болмайды.",
        "en": "A payment with invalid requisites cannot be approved.",
    },
    "error.trust_not_allowed": {
        "ru": "Доверие недоступно для этого платежа",
        "kk": "Бұл төлем үшін шотқа сенім білдіру қолжетімсіз.",  # review-kk
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
            "Қызыл деңгейлі төлемді мақұлдау үшін директордың түсініктемесі міндетті "
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
        "kk": "Сұрау денесіндегі JSON пішімі қате.",
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
        "kk": "мәні нақты сан болуы тиіс (NaN және шексіздіксіз).",
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
        "kk": "дұрыс санды көрсетіңіз.",
        "en": "please provide a valid number.",
    },
    "val.string_type": {
        "ru": "значение должно быть строкой.",
        "kk": "мәні мәтін жолы болуы тиіс.",
        "en": "value must be a string.",
    },
    "val.bool_parsing": {
        "ru": "значение должно быть логическим (true/false).",
        "kk": "мәні логикалық (true/false) болуы тиіс.",
        "en": "value must be a boolean (true/false).",
    },
    "val.literal_error": {
        "ru": "недопустимое значение (ожидается: {expected}).",
        "kk": "жарамсыз мән (күтілетіні: {expected}).",
        "en": "invalid value (expected: {expected}).",
    },
    "val.recipient_name_required": {
        "ru": "Укажите название получателя.",
        "kk": "Алушының атауын көрсетіңіз.",
        "en": "Please enter the recipient name.",
    },
    "val.amount_finite": {
        "ru": "Сумма платежа должна быть конечным числом.",
        "kk": "Төлем сомасы нақты сан болуы тиіс.",
        "en": "Payment amount must be a finite number.",
    },
    "val.value_error_fallback": {
        "ru": "Некорректное значение поля.",
        "kk": "Өріс мәні қате.",
        "en": "Invalid field value.",
    },
    "val.generic": {
        "ru": "некорректное значение.",
        "kk": "қате мән.",
        "en": "invalid value.",
    },
}

FIELD_LABELS: dict[str, dict[Lang, str]] = {
    "payer_id": {"ru": "Плательщик", "kk": "Төлеуші", "en": "Payer"},
    "recipient_name": {"ru": "Название получателя", "kk": "Алушының атауы", "en": "Recipient name"},
    "recipient_bin": {"ru": "БИН/ИИН получателя", "kk": "Алушының БСН/ЖСН", "en": "Recipient BIN/IIN"},
    "recipient_iik": {"ru": "ИИК получателя", "kk": "Алушының ЖСК", "en": "Recipient IIK"},
    "recipient_bik": {"ru": "БИК банка", "kk": "Банктің БСК", "en": "Bank BIK"},
    "amount_kzt": {"ru": "Сумма платежа", "kk": "Төлем сомасы", "en": "Payment amount"},
    "purpose": {"ru": "Назначение платежа", "kk": "Төлем мақсаты", "en": "Payment purpose"},
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
}


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
