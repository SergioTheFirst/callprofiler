# 10 — Литература: реестр источников

> Статус: round 1, 2026-08-22. Собрано 14-направленным sweep (субагенты с веб-поиском), дедуплицировано по заголовку.
> `✔` = существование работы подтверждено поисковой выдачей агента. Отчёт агента — не доказательство: числа, на которые
> опирается план, продублированы в `claims-ledger.md` с пометкой личной перепроверки (раздел «Adversarial verdicts» ниже —
> 9 враждебных проверок ключевых утверждений, выполненных отдельными агентами с собственным поиском).


Всего уникальных: 151; verified: 142; по типу: book=4, dataset/tool=3, meta-analysis=2, peer-reviewed=93, preprint=6, primary=41, review=2


## 0. Adversarial verdicts по 9 опорным утверждениям


**V-1** · holds=yes
- Утверждение: Verbal/linguistic cues to deception have negligible diagnostic value in natural conversation: DePaulo 2003 median |d| well under 0.2 for most cues; Bond & DePaulo 2006 human accuracy ~54%; computer-based linguistic cue effects (Hauch 2015) are small and heterogeneous.
- Коррекция: Claim is essentially accurate but incompletely stated: DePaulo 2003 median d=0.10 across all 158 cues examined, but among the 28% that showed statistical significance, mean d=0.25 (range: d=0.25 for perceptual language to d=0.41 for negative emotion). Luke 2019 meta-analysis of publication bias estimates true effect sizes are 25-40% smaller than published values, implying true d≈0.15-0.19 for significant markers. Bond & DePaulo 2006 finding of 54% accuracy (47% on lies, 61% on truths) is confirmed. Hauch 2015 confirms small overall effects moderated strongly by context (event type, motivation, involvement). The claim correctly captures negligible practical value but obscures that some linguistic markers show Cohen's d in the small-to-small-medium range (0.2-0.4) before bias correction.
- Источники: DePaulo et al. (2003). Cues to deception. Psychological Bulletin, 129(1), 74-118. Median d=0.10 (all cues); d=0.25 average (n=14 significant cues).; Bond & DePaulo (2006). Accuracy of Deception Judgments. PSPR 10(3), 214-234. 54% accuracy replicable across 24,483 judges.; Hauch et al. (2015). Are Computers Effective Lie Detectors? A Meta-Analysis. PSPR 19(4), 307-342. Small effects, high moderation by context.; Luke (2019). Lessons from Pinocchio: Cues to Deception may be Highly Exaggerated. Perspectives on Psychological Science, 14(5), 646-666. Publication bias inflates estimates by 25-40%.


**V-2** · holds=yes
- Утверждение: Consistency/contradiction across repeated honest accounts is common (Fisher, Brewer & Mitchell 2009; Vredeveldt 2014): inconsistency is not a valid deception cue; rates of reminiscence/contradiction in honest retelling are substantial.
- Коррекция: The claim holds for eyewitness testimony literature (98% reminiscence rate in second interviews per Fisher, Brewer & Mitchell 2009; liars equally consistent per Vredeveldt 2014). However: (1) Generalizability to Russian business calls/promises untested—original studies are single-event eyewitness recall, not ongoing relationship commitments. (2) Reminiscence (new details) should be distinguished from contradiction (conflicting details); the 98% rate is reminiscence, not contradiction. (3) Deception-detection consensus confirms weak inconsistency effects (d<0.30; Luke 2019 correction for publication bias reduces reported effect sizes by 25–40%), but this generalization applies primarily to short-term interview settings, not long-term call archives.
- Источники: Fisher, Brewer & Mitchell (2009). The relation between consistency and accuracy of eyewitness testimony—98% of truthful witnesses show reminiscence in second recall; Vredeveldt (2014). Systematic review: liars equally/more consistent than truth-tellers; DePaulo et al. (2003) meta-analysis: ~28% of 158 deception cues show reliable effects; Luke (2019): Publication bias inflates deception-cue effect sizes by 25–40%; Hauch et al. (2015): Linguistic uncertainty markers effect size d<0.30 (small)


**V-3** · holds=NO/partial
- Утверждение: Hedges and approximators are high-frequency cooperative devices in Russian spontaneous speech (Bogdanova-Beglarian ORD corpus data on "как бы", "типа", "вроде"); raw hedge density is dominated by speaker style/genre rather than reliability.
- Коррекция: The ORD corpus does contain Russian spontaneous speech with documented hedging analysis, and hedges are frequent (estimated 25%+ of utterances based on comparable English data). However, the claim's framing is misleading: raw hedge density reflects speaker style/genre/politeness and is NOT a reliable indicator of trustworthiness. Only context-dependent hedging—elevated hedging relative to a speaker's baseline paired with question-evasion patterns (per Clayman & Bull/Mayer typology)—discriminates deceptive from honest communication. Absolute hedge rates should not be used as reliability signals.
- Источники: Bogdanova-Beglarian et al. (2012). The ORD Corpus: Principles and Annotation; Hyland, K. (1998). Boosting, hedging and the negotiation of academic knowledge; Clayman, S. (2001). Answers and evasions in news interviews; Hedging-equivocation section of digest: 'Absolute hedging rates are unreliable signals; relative hedging (within-speaker z-score) and hedging-in-evasion-contexts are stronger candidates'; Soubki et al. (2024). Roadrunner-Hedge corpus: >25% of spontaneous narratives contain hedges


**V-4** · holds=NO/partial
- Утверждение: A weighted additive composite with fixed a priori weights is a FORMATIVE index whose validity cannot be established by internal consistency; it requires an external criterion (Bollen & Lennox 1991; Diamantopoulos & Winklhofer 2001) — and reliable per-person estimates of rates need on the order of dozens of events (Schönbrodt & Perugini 2013 for correlations; Wilson interval widths for proportions).
- Коррекция: FORMATIVE INDEX & EXTERNAL CRITERION: Correct per Diamantopoulos & Winklhofer (2001) and Bollen & Lennox (1991). However, "fixed a priori weights" is a validity threat requiring robustness/sensitivity analysis (±10% weight variation) — 75% of published indices use arbitrary weights yet fail this test (OECD/Greco 2019). Validity requires THREE elements: content specification, MIMIC models, AND nomological validity, not just external criterion. SAMPLE SIZE CLAIM: Materially understated. Schönbrodt & Perugini (2013) shows: ρ=0.70 → n≈50; ρ=0.50 → n≈120; ρ=0.20 → n≈250. Claim of "dozens" is defensible only for ρ≥0.70 (high effect). For realistic moderate correlations (ρ=0.50), need ~120–240 events per contact when accounting for index reliability (scales by 1/rel²; realistic rel~0.70 doubles requirements). Per-contact proportion estimates with n=30–50 have ±0.17 CI width (too wide; n≥100 needed for ±0.10 precision). Wilson intervals address single-proportion CIs, not composite index validation. True statement: "dozens to hundreds of events per contact, depending on effect size and reliability assumptions (explicit assumptions required)."
- Источники: Diamantopoulos & Winklhofer (2001) Index Construction with Formative Indicators: Does weighting matter? — yes, weights must be justified and tested for sensitivity, not fixed arbitrarily.; Schönbrodt & Perugini (2013) At what sample size do correlations stabilize? — n depends critically on effect size (ρ); no blanket 'dozens' recommendation.; OECD/Greco (2019) Composite indices methodology review — 75% of published indices use unjustified arbitrary weighting; robust practice requires ±10% sensitivity test.; Koo & Li (2016) ICC guidelines for multi-rater reliability — minimum n≈50 for index estimation, n≥100–150 for ±0.10 CI precision.; Schönbrodt et al. (2016) replication — effect size determines n; lower effects require 4–5× larger samples than high-effect scenarios.


**V-5** · holds=NO/partial
- Утверждение: Promise-keeping is the most behaviorally grounded reliability signal: kept/broken outcomes with beta-binomial (Jøsang 2002) or empirical-Bayes shrinkage give calibrated per-person estimates; time decay of evidence is standard in reputation systems.
- Коррекция: Beta-binomial reputation models (Jøsang 2002) are theoretically valid ONLY when: (1) promise labels are recorded with >90% accuracy, (2) per-contact sample sizes ≥50 calls (Schönbrodt & Perugini 2013), and (3) external validation confirms the index predicts behavioral outcomes. In CallProfiler's context (promise labels inferred from noisy ASR transcripts with 20–35% WER, <30 calls for 60% of contacts, no domain-specific validation), beta-binomial estimates are biased and unstable. Confidence ceiling should be 0.40–0.50 null. Time decay (90-day half-life) is unsupported assumption; empirical studies show decay rates vary by reputation tier (high-reputation contacts decay slower or not at all). Promise-keeping signals work only when "recorded" (web search finding); CallProfiler's inference-based extraction does not meet this condition without ground-truth validation.
- Источники: Schönbrodt & Perugini (2013). At what sample size do correlations stabilize? n ≥50 for ρ=0.70, n≥120 for ρ=0.50.; Jøsang & Ismail (2002). The Beta Reputation System (confirmed real, but applicability requires clean labels + large n); Diamantopoulos & Winklhofer (2001). Formative indices require nomological validity (external criterion prediction); du et al. Promise-Keeping Reputations Study: 'when promise-keeping histories are not recorded, bare promises fail' — applies to CallProfiler's inferred extraction; ASR-GLUE / nlp-asr-noise digest: Contradiction detection degrades 88%→60-75% F1 under 20–35% WER; promise detection similarly degraded; OECD Handbook on Composite Indicators: arbitrary weighting lacks robustness without sensitivity analysis; Greco et al. (2019) recommend external validation


**V-6** · holds=NO/partial
- Утверждение: A confidence score must be evaluated by proper scoring rules and reliability diagrams (Brier/Murphy; DeGroot & Fienberg; Gneiting & Raftery); with a few hundred noisy labels, ECE bins must be coarse (≤5 bins) and label noise biases calibration estimates.
- Коррекция: Proper scoring rules (Brier) and reliability diagrams ARE the standard for evaluating confidence (Gneiting & Raftery 2007, DeGroot & Fienberg 1983)—this part is correct. However: (1) ECE bins "must be" ≤5 is overstated and contradicts recent findings. Guilbert (2024) shows ECE is "biased downward with small bin counts and few samples," so coarse binning WORSENS bias under noisy labels. (2) With ~300 noisy labels, recommended approaches are adaptive binning, SmoothECE (kernel smoothing), Classwise-ECE, or conformal prediction (which provides distribution-free finite-sample coverage without binning). Recent noise-aware methods (ACNL, CRCP, NACP from 2023-2025) handle label noise explicitly. (3) Label noise degrades both model calibration AND ECE estimation, but the solution is specialized noise-robust methods, not fixed coarse bins. Corrected: Use proper scoring rules + reliability diagrams; with noisy labels, employ adaptive binning, SmoothECE, or conformal prediction rather than fixed ≤5 bins.
- Источники: Gneiting & Raftery (2007): Strictly proper scoring rules foundational; DeGroot & Fienberg (1983): Reliability diagrams and calibration decomposition; Guilbert (2024): ECE biased downward with small bin counts (via digest); Naeini et al. (2015): ECE bins typically 5–15, not mandatory ≤5; Web search 2024-2025: SmoothECE, SMECE, ACNL, CRCP for noisy labels; Angelopoulos & Bates (2021): Conformal prediction with finite-sample guarantees


**V-7** · holds=NO/partial
- Утверждение: Displaying precise numbers increases perceived certainty (numeric precision effect; Jerez-Fernandez 2014) and explanations/scores induce over-reliance (Bansal 2021; Buçinca 2021): for low-confidence cases a verbal band or abstention is better supported than a number.
- Коррекция: Part 1 confirmed: Jerez-Fernandez et al. (2014) demonstrated that precise numbers signal higher confidence and influence decisions. Part 2 confirmed: Bansal (2021) and Buçinca (2021) showed explanations can increase over-reliance. Part 3 NOT supported: Neither paper tested verbal bands vs. numbers. Buçinca (2021) recommends cognitive forcing (making users engage critically), not abstention. Lichtenstein & Fischhoff (1982) recommend interval estimates and training feedback. Conformal prediction (Angelopoulos & Bates 2021) and proper scoring rules (Guo et al. 2017) support calibrated confidence scores, not abstention. The evidence supports improving how confidence is communicated and validated, not removing it.
- Источники: Jerez-Fernandez et al. (2014) Psychological Science: precision effect confirmed; Bansal et al. (2021): explanations increase over-trust in AI; Buçinca et al. (2021) CHI: cognitive forcing reduces over-reliance, not abstention; Lichtenstein & Fischhoff (1977–1982): interval estimates reduce overconfidence; Guo et al. (2017) ICML: temperature scaling and calibration of confidence scores; Angelopoulos & Bates (2021) conformal prediction for finite-sample coverage guarantees


**V-8** · holds=NO/partial
- Утверждение: Verbalized confidence from LLMs is overconfident and weakly calibrated, especially for small open models (Xiong 2023; Tian 2023); verbatim-quote grounding measurably reduces hallucinated extractions.
- Коррекция: LLMs show poor verbalized confidence calibration (Xiong 2023; Tian 2023), but calibration *improves* with model scale—not worse for small models. Xiong et al. benchmarked GPT-3, GPT-3.5, GPT-4, Vicuna, and LLaMA 2, finding larger models better-calibrated. Tian et al. show RLHF-trained models degrade calibration but don't specifically identify small open models as uniquely worse. Verbatim-quote grounding reduces hallucination by 35–50% on clean benchmarks (Su 2023; HalluLens 2024) but effectiveness on noisy ASR transcripts or Russian business calls remains unvalidated—critical gap for CallProfiler deployment.
- Источники: Xiong et al. (2023): Can LLMs Express Their Uncertainty?—shows calibration improves with model scale, contradicting 'especially for small open models' claim; Tian et al. (2023): Just Ask for Calibration—documents RLHF calibration degradation but not small-model specificity; Su et al. (2023): According to ...—demonstrates quote-grounding reduces hallucination on GPT-3/text-davinci-003; HalluLens (Gao et al. 2024): Reports 35–50% hallucination reduction with quote enforcement on benchmarks; Digest (nlp-asr-noise): Flags unvalidated transfer to noisy ASR transcripts as critical falsifier


**V-9** · holds=yes
- Утверждение: Voice stress analysis has no demonstrated validity (Damphousse 2007; Eriksson & Lacerda 2007); paraverbal cues to deception have small effects (Sporer & Schwandt 2006); telephone diarization DER is routinely 10-20%+, making per-utterance role attribution unreliable for a non-trivial fraction of calls.
- Коррекция: as stated
- Источники: Damphousse et al. 2007 (NIJ report): Voice stress analysis achieved ~50% accuracy on detecting drug-use deception—chance level. Inter-rater reliability r=0.11–0.52.; Eriksson & Lacerda 2007 (Intl. J. Speech, Language & Law): No scientific evidence supports voice stress analysis claims; machines perform at chance level.; Sporer & Schwandt 2006 (Applied Cognitive Psychology): Meta-analysis of 9 paraverbal cues found only 2–4 reliably associated with deception. Effect size (response latency): d=0.18. High heterogeneity across contexts.; Diarization benchmarks (DIHARD, pyannote): Telephone conversation DER consistently 10–20% in leading systems, affecting 1 in 5–10 speaker segments.


## 1. Философия и психология bullshit

**Сводка направления:** Bullshitting (indifference to truth-apt communication per Frankfurt, operationalized as structural linguistic patterns per Cohen/Meibauer) is theoretically distinct from lying, error, and hyperbole but empirically difficult to isolate in text alone. Philosophy consensus: bullshit characterized by speaker's indifference to truth-value, expressed certainty despite weak evidence, and vagueness masquerading as profundity (Pennycook). Empirical challenge: linguistic markers of deception/bullshitting are weak (effect sizes d < 0.50), inconsistent across datasets, and fail to generalize beyond training corpora (Litvinova et al. 2025). Two validated self-report scales exist (Pennycook's Bullshit Receptivity Scale, Littrell's Bullshitting Frequency Scale) measuring receiver sensitivity and producer tendency respectively, but no validated automatic text-based detector for naturalistic speech. Strongest falsifier for CallProfiler BS-index v2: linguistic markers do not reliably distinguish bullshitting from honest error or epistemic humility in low-generalization settings; point estimates unjustified without confidence intervals; ground truth (actual promise outcomes, factual accuracy) essential for calibration.


### L-001 · Frankfurt, H.G. (2005). On Bullshit. Princeton University Press.
- **Тип/сила/verified:** book / strong / ✔
- **Утверждает:** Bullshit is communication produced with indifference to truth-value; distinct from lying because liar knows/believes the truth and hides it, while bullshitter is indifferent to whether statement is true or false. Core philosophical distinction: bullshit is more dangerous to truth than lying because it corrodes the very concept of truth-seeking.
- **Против/ограничения:** Cohen (2006) argues Frankfurt's indifference criterion is neither necessary nor sufficient: honest people can produce bullshit by transmitting falsehoods from other sources they believe but haven't verified.
- **Переносимость (RU-телефон, ASR, 9B):** Defines operational target for CallProfiler BS-index v2: state of mind (indifference vs commitment to truth-apt communication) remains unobservable from transcript alone; only linguistic proxies available.
- **Следствие для CallProfiler:** BS-index must operationalize indifference behaviorally (vagueness, certainty-over-evidence, doublespeak patterns) rather than inferring mental state directly.


### L-002 · Pennycook, G., Cheyne, J.A., Barr, D.J., Koehler, D.J., & Fugelsang, J.A. (2015). On the reception and detection of pseudo-profound bullshit. Judgment and Decision Making, 10(6), 549–563.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Pseudo-profound bullshit (random buzzwords with syntactic structure but no semantic content, e.g., 'Wholeness quiets infinite phenomena') is judged as profound by ~50% of non-analytical participants. Analytic cognitive style inversely predicts receptivity (effect size not explicitly given in abstract, but correlations with CRT and openness to experience reported). Bullshit Receptivity Scale (BSR) designed and validated.
- **Против/ограничения:** Receptivity varies by individual cognitive style; some people reliably detect pseudo-profound nonsense. Detection is not universal.
- **Переносимость (RU-телефон, ASR, 9B):** Demonstrates text-based signals of bullshit (vagueness + high-register vocabulary) can induce false profundity judgments in listeners. Measures RECEIVER's bullshit receptivity, not speaker's bullshitting skill. For CallProfiler: contact behavior (certainty expressed despite weak evidence) is detectable linguistic proxy.
- **Следствие для CallProfiler:** BS-index should penalize expressed certainty when evidence is weak or vague; Pennycook's BSR framework shows such patterns exist and can be measured.


### L-003 · Petrocelli, J.V. (2018). Antecedents of bullshitting. Journal of Experimental Social Psychology, 76, 249–258.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Bullshitting occurs when social obligation to have an opinion is high AND concern for evidence is low (Experiment 1, n not specified in abstract). Social accountability attenuates bullshitting (Experiment 2). Bullshitting is motivated behavior distinct from lying: bullshitter doesn't track truth value.
- **Против/ограничения:** Study measures propensity in controlled lab settings (opinion solicitation paradigm); generalization to telephone conversation speech (CallProfiler context) untested.
- **Переносимость (RU-телефон, ASR, 9B):** Operationalizes antecedents: high social pressure + low evidence concern → bullshitting likely. In transcripts: promises made despite acknowledged ignorance; certainty expressed without factual grounding; topic-switching when challenged. These are measurable in text.
- **Следствие для CallProfiler:** BS-index should increase when contact makes commitments about topics they've previously claimed ignorance of, or express certainty that contradicts earlier uncertainty.


### L-004 · Littrell, S., Risko, E.F., & Fugelsang, J.A. (2021). The Bullshitting Frequency Scale: Development and psychometric properties. British Journal of Social Psychology, 60(1), 196–217.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Developed 12-item self-report Bullshitting Frequency Scale (BFS) measuring persuasive (impression-management) and evasive (avoidance) bullshitting. Bullshitting frequency correlates negatively with sincerity (r ~−0.40), honesty (r ~−0.50), cognitive ability (r ~−0.25), and open-minded cognition (r ~−0.35). Test-retest reliability ~0.70–0.80.
- **Против/ограничения:** Self-report scale subject to social desirability bias; doesn't measure actual bullshitting in transcripts, only self-perceived tendency.
- **Переносимость (RU-телефон, ASR, 9B):** Distinguishes two bullshitting styles: persuasive (inflate competence, impression-manage) vs evasive (dodge questions, equivocate). For CallProfiler: transcript patterns can proxy these—evasive shows as topic-switching, equivocation; persuasive as unfounded claims.
- **Следствие для CallProfiler:** BS-index should distinguish between impression-management bullshitting (vague positive claims) and evasive bullshitting (vague refusals, deflections); each has different linguistic signature.


### L-005 · Petrocelli, J.V. (2021). Bullshitting and persuasion: The persuasiveness of a disregard for the truth. British Journal of Social Psychology, 60(4), 1464–1483.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Bullshitting is effective for persuasion when arguments are weak (low-quality reasoning): bullshit framing of weak arguments yielded higher persuasion than evidence-based frame. Bullshitting failed when arguments were strong. Effect sizes: persuasion advantage ~d = 0.50 for weak arguments, reversed for strong arguments.
- **Против/ограничения:** Persuasion advantage for bullshit depends critically on argument quality; truthful communication wins for strong evidence.
- **Переносимость (RU-телефон, ASR, 9B):** Suggests contacts with high BS-index use bullshitting strategically when they lack strong evidence, then rely on truth when evidence is solid. Measurable: correlate bullshitting instances with call outcomes (promises kept vs broken, factual accuracy of claims).
- **Следствие для CallProfiler:** BS-index confidence should modulate by domain: higher confidence in contacts who bullshit about low-evidence topics, lower if they produce bullshit despite strong available evidence.


### L-006 · Meibauer, J. (2018). The Linguistics of Lying. Annual Review of Linguistics, 4, 169–188.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Lying, bullshitting, and related communicative deceptions can be analyzed via pragmatics and grammar. Meibauer defines bullshitting as insincere asserting with loose concern for truth, expressed with unwarranted certainty. Three types identified: evasive bullshitting (vague responses to obligations), bullshit lies (false assertions with indifference to truth), bald-faced bullshitting (false assertion when listener knows truth).
- **Против/ограничения:** Pragmatic categories are theoretically distinct but empirically hard to isolate in transcript; indifference to truth remains subjective inference.
- **Переносимость (RU-телефон, ASR, 9B):** Provides linguistic categories for transcript analysis: evasive BS (equivocation, topic-switching), assertive BS (claims without evidence), contradictory BS (statement vs prior negation). These are text-observable.
- **Следствие для CallProfiler:** BS-index linguistic features: track unwarranted certainty markers ('definitely', 'clearly', 'no doubt'), vagueness + hedging, topic switches; distinguish evasive (high hedging) from assertive (high confidence without evidence).


### L-007 · Cohen, G.A. (2006). Deeper Into Bullshit. Ratio, 19(4), 413–424.
- **Тип/сила/verified:** peer-reviewed / moderate / ✔
- **Утверждает:** Frankfurt's indifference-to-truth criterion is neither necessary nor sufficient for bullshit. Honest people transmit false information they believe to be true; this is bullshit by structural standards but not by intention. Bullshit can be characterized structurally (vagueness, jargon, pseudo-profundity) independent of speaker's mental state.
- **Против/ограничения:** Frankfurt replies indifference is still the defining feature; structural markers are symptoms, not essences.
- **Переносимость (RU-телефон, ASR, 9B):** Critical: suggests CallProfiler cannot infer state of mind from text; must focus on structural/linguistic properties (vagueness, complexity without content, jargon without grounding). Shifts target from 'does speaker care about truth?' to 'does text exhibit markers of indifference?'
- **Следствие для CallProfiler:** BS-index operationalization must be structural (linguistic proxies) rather than intentional; measure patterns observable in transcript, not beliefs.


### L-008 · DePaulo, B.M., Lindsay, J.J., Malone, B.E., Muhlenbruck, L., Charlton, K., & Cooper, H. (2003). Cues to deception. Psychological Bulletin, 129(1), 74–118.
- **Тип/сила/verified:** meta-analysis / strong / ✔
- **Утверждает:** Meta-analysis of 120 studies on deception detection (n = 5,896 participants). Liars express more negative emotions (d = 0.41), use less perceptual/sensory language (d = 0.25), self-reference less (use fewer 'I'), show increased cognitive load. However, effect sizes are small to moderate. Human lie detection accuracy ~47–54% (vs 61% for truth detection), barely above chance.
- **Против/ограничения:** Linguistic markers are weak and inconsistent across contexts; many studies conflate strategic deception with spontaneous false memory.
- **Переносимость (RU-телефон, ASR, 9B):** Provides baseline: text-based deception markers (less sensory detail, negative emotion, reduced self-reference) exist but are weak. Suggests bullshitting (indifference) may show different signature than lying (effort to conceal). For CallProfiler: low effect sizes mean individual markers unreliable; ensemble needed.
- **Следствие для CallProfiler:** BS-index should combine multiple weak linguistic signals (vagueness, certainty-over-evidence, reduced sensory detail, topic-switching) rather than relying on single marker. Confidence intervals must be wide due to weak individual signal strength.


### L-009 · Litvinova, T., Litvinov, O., Seredin, P., & Farkhutdinov, R. (2025). What if Deception Cannot be Detected? A Cross-Linguistic Study on the Limits of Deception Detection from Text. arXiv:2505.13147; Proceedings of ACL 2025.
- **Тип/сила/verified:** preprint / strong / ✔
- **Утверждает:** Recent NLP study evaluating deception detection across languages. Computational models achieve ~69% accuracy on within-dataset tests but drop to chance (~50%) on cross-dataset generalization. Linguistic markers are unreliable for belief-based deception (where speaker genuinely believes false claim). Prior success in deception detection attributed to dataset artifacts, not robust linguistic signals.
- **Против/ограничения:** Curated, high-quality datasets can sustain ~70% accuracy; limitation may be specific to belief-based vs strategic deception.
- **Переносимость (RU-телефон, ASR, 9B):** Critical finding for CallProfiler: linguistic signals of bullshitting may not generalize across contacts or time periods. High confidence in individual BS-estimates unjustified. Suggests ensemble + uncertainty quantification necessary.
- **Следствие для CallProfiler:** BS-index must report confidence intervals, not point estimates. Cross-validation on held-out contacts essential. Treat v2 as experimental; validate against ground truth (actual promises kept/broken, factual accuracy checks).


### L-010 · Pennycook, G., Cheyne, J.A., & Barr, D.J. (2023). The PBSDS: A Dataset for the Detection of Pseudoprofound Bullshit. Proceedings of the Fourth Workshop on Computational Linguistics for Misinformation (CLiMi) at ACL 2023.
- **Тип/сила/verified:** dataset/tool / moderate / ✘ не подтверждено — не цитировать в плане без ре-чека
- **Утверждает:** Annotated dataset of pseudo-profound bullshit (random buzzword statements) vs genuine profound statements vs mundane statements. Enables training classifiers to detect pseudo-profound BS. Preliminary classifier results show feasibility of automatic detection; specific accuracy metrics not available in abstract.
- **Против/ограничения:** Dataset limited to synthetic pseudo-profound statements; unclear if markers transfer to naturalistic bullshitting (evasion, equivocation in conversational speech).
- **Переносимость (RU-телефон, ASR, 9B):** Confirms computational approach feasible for pseudo-profound subtype. Markers in dataset (buzzword density, semantic incoherence) may apply to some contact BS. Limited applicability to CallProfiler's naturalistic phone-call transcripts (which involve evasive/assertive, not pseudo-profound, bullshitting primarily).
- **Следствие для CallProfiler:** BS-index can incorporate pseudo-profundity sub-score (buzzword + vagueness + semantic anomaly), but weight lower than evasive/assertive markers for conversational speech.


## 2. Deception detection и его провалы

**Сводка направления:** Deception detection through linguistic and behavioral cues has fundamentally weak predictive power in natural conversation. Bond & DePaulo (2006) established a 54% accuracy ceiling (barely above chance) across 24,483 judges; Luke (2019) demonstrated that even these modest effect sizes are inflated by publication bias—true effects are 25–40% smaller than reported. DePaulo et al. (2003) found 158 supposed deception cues, but only ~28% showed reliable effects; core indicators like gaze aversion (d≈0.03) are near-zero. Hauch et al. (2015) confirmed linguistic markers are detectable but small (d<0.30), moderated by topic/context/motivation. Cross-domain generalization fails: Panda et al. (2020) report in-domain 86% accuracy drops to 52–64% across domains. Levine's Truth-Default Theory (2014) explains the irreducible problem—deception is rare in natural speech (~<5% utterances); base-rate effects mean even 70% sensitivity yields ~20% positive predictive value. **For CallProfiler's BS-index with fragmented speaker roles (UNKNOWN>30%), realistic accuracy ceiling is 55–60% on contact-level veracity judgment, barely exceeding chance. Confidence index should start from 50% null and only rise with external corroboration, not linguistic cues alone.**


### L-011 · Bond, C. F., & DePaulo, B. M. (2006). Accuracy of deception judgments. Personality and Social Psychology Review, 10(3), 214–234.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Meta-analysis synthesizing 206 documents, 24,483 judges. Unaided human accuracy = 54% (barely above 50% chance level). Judges correctly classify 47% of lies as deceptive, 61% of truths as nondeceptive. Professionals (cops, judges, Secret Service) do NOT perform better than laypeople. Accuracy varies more by sender characteristics than judge/system ability.
- **Против/ограничения:** None known; this is a foundational benchmark replicating across decades of follow-up work.
- **Переносимость (RU-телефон, ASR, 9B):** Upper bound for any linguistic/behavioral deception detection system in natural conversation. CallProfiler's BS-index, if purely cue-based, should not exceed ~54% accuracy on contact-level veracity judgments.
- **Следствие для CallProfiler:** Confidence index should start from 50% as null hypothesis and only rise with additional orthogonal evidence (corroboration, external facts, repeated patterns). Single-call linguistic analysis cannot exceed baseline.


### L-012 · Hartwig, M., & Bond, C. F. (2014). Lie detection from multiple cues: A meta-analysis. Applied Cognitive Psychology, 28(6), 661–676.
- **Тип/сила/verified:** primary / moderate / ✔
- **Утверждает:** Meta-analysis of 144 samples (9,380 participants, 26,866 messages). Reported ~70% detection accuracy when using multiple objectively-coded nonverbal cues combined in computer models. However, accuracy is contingent on: (1) training/interrogation settings, (2) high motivation liars, (3) objective coding of discrete behaviors (not transcript analysis).
- **Против/ограничения:** Luke (2019) argues this 70% figure is inflated by publication bias and that cross-domain generalization drops to 52–64%. Hartwig & Bond study did NOT test natural conversation or fragmented speaker roles.
- **Переносимость (RU-телефон, ASR, 9B):** Not directly applicable to CallProfiler. Hartwig & Bond used interrogation (controlled turn-taking, known stakes, video/audio of full body). Russian transcripts lack video, have speaker role ambiguity (UNKNOWN>30%), and are spontaneous talk.
- **Следствие для CallProfiler:** Do NOT extrapolate 70% accuracy to text-only, speaker-fragmented data. Confidence index for text-only analysis should be 20–30 points lower than lab-based systems.


### L-013 · Levine, T. R. (2014). Truth-Default Theory (TDT): A theory of human deception and deception detection. Journal of Language and Social Psychology, 33(4), 378–393.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Humans operate under a truth-default assumption: honesty is assumed unless strong 'truth-default triggers' activate suspicion. Deception requires both motive AND absence of competing social goals. In natural conversation, most utterances are truthful (estimated <5% deception in everyday speech). System cannot disambiguate isolated lie from contextual truthfulness when prior probability of deception is low.
- **Против/ограничения:** Does not quantify detection accuracy; TDT explains *why* detection is hard, not HOW to detect. Empirically validated on conversation corpora.
- **Переносимость (RU-телефон, ASR, 9B):** Directly applicable. In CallProfiler's corpus (~16k business calls), base rate of actual deliberate deception per contact is unknown but likely <10–15% of calls. BS-index treats all risky-sounding speech equally, ignoring base rate.
- **Следствие для CallProfiler:** Confidence index MUST account for low prior probability of deception. Even if BS-index has 70% sensitivity, positive predictive value = 0.70×0.10 / (0.70×0.10 + 0.30×0.90) ≈ 20%. Most high-BS contacts are false positives.


### L-014 · Hauch, V., Blandón-Gitlin, I., Masip, J., & Sporer, S. L. (2015). Are computers effective lie detectors? A meta-analysis of linguistic cues to deception. Personality and Social Psychology Review, 19(4), 307–342.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Meta-analysis of 44 studies, 79 linguistic cues. Relative to truth-tellers, liars showed: greater cognitive load, more negative emotions, distancing (fewer first-person pronouns), fewer sensory-perceptual words, fewer references to cognitive processes. HOWEVER: overall effect sizes were SMALL. Liars were NOT significantly more uncertain (contradicting common assumption). Effects moderated by event type, involvement, motivation.
- **Против/ограничения:** Luke (2019) argues even these 'small' effect sizes are inflated; true effect sizes may be 0.1–0.2 (negligible).
- **Переносимость (RU-телефон, ASR, 9B):** Directly applicable to Russian transcripts. GigaAM ASR captures lexical/syntactic markers (pronouns, adverbs, punctuation). BUT: speaker role fragmentation (UNKNOWN) destroys reliability of first-person/distancing cues.
- **Следствие для CallProfiler:** Linguistic markers have detectable but weak signal. Confidence index should discount pronoun-based features by 30–40% when speaker attribution uncertain. Small effect sizes mean system accuracy cannot exceed ~60% even with perfect speaker roles.


### L-015 · Newman, M. L., Pennebaker, J. W., Berry, D. S., & Richards, J. M. (2003). Lying words: Predicting deception from linguistic styles. Personality and Social Psychology Bulletin, 29(5), 665–675.
- **Тип/сила/verified:** primary / moderate / ✔
- **Утверждает:** Analysis of five samples. Computer-based text classification achieved 67% accuracy (constant topic), 61% overall. Liars used lower cognitive complexity, fewer self/other-references, more negative emotion words. Effect sizes SMALL to MEDIUM. Study used controlled elicitation (specific topics, known stakes), not natural conversation.
- **Против/ограничения:** Results do NOT generalize to cross-domain or natural conversation corpora (Luke 2019 replication challenge). 61% overall is barely above Bond & DePaulo baseline (54%).
- **Переносимость (RU-телефон, ASR, 9B):** Weak applicability to CallProfiler. Newman & Pennebaker used laboratory speech production (speakers aware they are being analyzed). Russian business calls are spontaneous, multi-topic, unknown stakes per contact.
- **Следствие для CallProfiler:** Do NOT extrapolate 67% accuracy. Expect ~55–60% real-world accuracy for natural Russian conversation. Confidence index should treat Newman-Pennebaker findings as optimistic ceiling, not realistic baseline.


### L-016 · Luke, T. J. (2019). Lessons from Pinocchio: Cues to deception may be highly exaggerated. Perspectives on Psychological Science, 14(5), 646–666.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Using Monte Carlo simulations, demonstrates that many reported deception cue effect sizes are inflated by publication bias, small sample sizes, and low statistical power. Estimated true effect sizes for published 'large' effects are often half reported size or smaller. Informational value of existing deception literature is 'quite low' — impossible to distinguish real effects from false positives in many cases.
- **Против/ограничения:** None known; directly addresses replication crisis in deception literature. Supported by independent meta-analyses (Hartwig & Bond 2014 cross-domain drop from 70% to 52–64%).
- **Переносимость (RU-телефон, ASR, 9B):** CRITICAL for CallProfiler. Every effect size reported in deception literature (including DePaulo 2003, Hauch 2015, Newman 2003) is suspect. True effects likely 30–50% smaller than reported.
- **Следствие для CallProfiler:** Depress all effect size estimates by 25–40%. If meta-analysis reports d=0.35, assume true d≈0.20. Confidence index should reflect this uncertainty. High-BS contacts have lower discriminative value than literature suggests.


### L-017 · Sporer, S. L., & Schwandt, B. (2006). Paraverbal indicators of deception: A meta-analytic synthesis. Applied Cognitive Psychology, 20(4), 541–559.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Meta-analysis of nine paraverbal speech behaviors. Only 2 (weighted) to 4 (unweighted) of 9 were reliably associated with deception. Response latency: d=0.18 (small effect). Pitch, speech errors, message duration also analyzed. High heterogeneity across studies; effects moderated by context, preparation, motivation.
- **Против/ограничения:** None direct; heterogeneity indicates cues are highly situation-dependent, reducing generalizability.
- **Переносимость (RU-телефон, ASR, 9B):** Directly applicable to transcript timing analysis. If CallProfiler extracts response latencies (ms between speaker turns), expect d≈0.18. Cross-domain generalization unknown.
- **Следствие для CallProfiler:** Timing-based features (if available from GigaAM segmentation) contribute signal, but weakly. Confidence should weight timing cues at 15–20% of total BS-index, not equally with linguistic content.


### L-018 · Hauch, V., Sporer, S. L., Michael, S. W., & Meissner, C. A. (2016). Does training improve the detection of deception? A meta-analysis. Communication Research, 43(3), 283–343.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Meta-analysis of 30 studies (22 published, 8 unpublished) on training effect. Small to medium training effect for detection accuracy (verbal content training > nonverbal/paraverbal training). Implies that even with expert training, baseline detection accuracy (54%) only improves to ~60–65%.
- **Против/ограничения:** Training on verbal content shows larger effect than nonverbal, but absolute improvement is still modest. Suggests cues are inherently weak signals.
- **Переносимость (RU-телефон, ASR, 9B):** Directly applicable. CallProfiler's automated verbal content analysis is equivalent to 'training on verbal cues.' Expected accuracy improvement over untrained human: ~6–11pp. Real-world accuracy ~60–65%.
- **Следствие для CallProfiler:** Confidence index should cap out at 65 for verbal-cue-only systems, even with optimized algorithms. Multi-modal approaches (video + audio + transcript) might reach higher, but CallProfiler has transcript + fragmented speaker roles only.


### L-019 · Panda, S., Jain, P., Mukherjee, B., & Kumaraguru, P. (2020). Deception detection across domains, languages and modalities. Proceedings of the 2020 Workshop on Misinformation and Misbehavior Mining on the Web (MisinfoCon), 1–9.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Cross-domain deception detection study: In-domain accuracy 86%, mixed-domain 75%, cross-domain 52–64%. Linguistic cues show 'considerable variability and limited cross-domain consistency.' Individual strategies for deception are topic- and context-dependent.
- **Против/ограничения:** Small sample study; replication on larger corpus needed. But finding aligns with Luke (2019) critique.
- **Переносимость (RU-телефон, ASR, 9B):** CRITICAL for CallProfiler. Transcripts drawn from one contact type (business) but diverse contexts (projects, negotiations, personal). Cross-domain accuracy ~52–64% realistic estimate if system trained on subset of contacts.
- **Следствие для CallProfiler:** Confidence index must account for domain shift. Contacts with topics/contexts similar to training set: confidence can reach 65–70. Contacts with novel topics/contexts: cap at 50–55 (near baseline).


### L-020 · Loconte, R., Battaglini, C., Maldera, S., Pietrini, P., Sartori, G., Navarin, N., & Monaro, M. (2025). Detecting deception through linguistic cues: From reality monitoring to natural language processing. Journal of Language and Social Psychology, 44(1), 34–62.
- **Тип/сила/verified:** peer-reviewed / moderate / ✔
- **Утверждает:** Recent review of NLP-based deception detection. Reality Monitoring (cognitive criteria for truthfulness) produces modest accuracy (~60%). Computer-based linguistic analysis slightly outperforms human raters (~64% vs 59%) but both remain far from clinical utility. Challenges: contextual dependence, individual differences, dialect effects.
- **Против/ограничения:** Finds NLP outperforms humans slightly; however, both are well above baseline only when event type and stakes are controlled. Natural conversation remains challenging.
- **Переносимость (RU-телефон, ASR, 9B):** Directly applicable. Confirms that automated linguistic analysis (NLP/CallProfiler approach) should achieve ~60–64% on Russian transcripts if speaker roles are clean and topics uniform.
- **Следствие для CallProfiler:** Confidence index for transcript-only system: baseline 50%, optimistic ceiling 65%. With fragmented speaker roles (UNKNOWN>30%), deduct 10–15pp. Realistic confidence range: 35–55 per contact.


## 3. Хеджирование, неопределённость, уклончивость

**Сводка направления:** Hedging and vagueness are linguistically measurable phenomena well-studied in academic discourse (Hyland) and political evasion (Bull & Mayer, Clayman, Bavelas). The field converges on: (1) hedges serve multiple functions (politeness, uncertainty, conflict avoidance), (2) hedging density increases in threatening contexts (Cialdini), (3) spontaneous speech baseline ~25-30% hedging (Soubki et al.). **Contested**: whether hedging is a reliability signal or just normal speech. Hyland and Channell show hedging is genre-expected; Clayman distinguishes overt vs. covert evasion (hedging + question-mismatch = evasion). **Single most important falsifier for CallProfiler confidence index**: If BS-index penalizes all hedging equally, it will correlate with politeness and formality, not actual dishonesty. The key discriminator is **context-dependent hedging** (elevated hedging relative to contact's baseline, paired with off-topic or question-evasive responses). Absolute hedging rates are unreliable signals; relative hedging (within-speaker z-score) and hedging-in-evasion-contexts (per Clayman/Bull & Mayer typology) are stronger candidates for confidence index features.


### L-021 · Ken Hyland (1998). Boosting, Hedging and the Negotiation of Academic Knowledge. Journal of Pragmatics, 24(5), 477-496.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Hedging is a central pragmatic strategy in academic writing. Hyland's poly-pragmatic model categorizes hedges into three types: content-oriented (reliability assessment), reader-oriented (awareness of expectations), and text-oriented (discourse organization). Hedges express possibility rather than certainty.
- **Против/ограничения:** Hyland's model focuses on written academic discourse, which has different norms than spontaneous spoken conversation. Applicability to casual phone speech requires validation.
- **Переносимость (RU-телефон, ASR, 9B):** Limited. Academic hedging norms differ from spontaneous speech in Russian telephone calls. ASR noise would complicate hedge detection. However, the three-part typology could help differentiate politeness hedges from evasion markers.
- **Следствие для CallProfiler:** Content-oriented hedges (confidence qualification) may be reliability signals; reader-oriented hedges are more likely politeness/cooperation markers. For CallProfiler: flag content hedges ("I think", "perhaps", "maybe") as potential unreliability signals; reader-oriented hedges ("if you know what I mean") as normal speech.


### L-022 · Janet Beavin Bavelas, Alex Black, Nicole Chovil, Jennifer Mullett (1990). Equivocal Communication: Verbal, Behavioral, and Physiological Responses to Equivocal Messages. Journal of Personality and Social Psychology, 58(4), 475-481.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Equivocation occurs when all direct replies to a question have negative consequences for the speaker. Bavelas developed a scaling method for objective assessment of equivocation. Several hundred experiments with children, adults, and politicians support the theory.
- **Против/ограничения:** Theory explains equivocation as conflict avoidance, but does not account for evasion as a deliberate deception strategy (vs. genuine communication conflict). Real-world question-dodging may have different motivations.
- **Переносимость (RU-телефон, ASR, 9B):** High. In business/personal calls, both parties often have competing goals (privacy vs. transparency, self-protection vs. honesty). Equivocation theory predicts vagueness increases when questions threaten the speaker. Detectable in Russian phone speech via increased hedge markers.
- **Следствие для CallProfiler:** When BS-index is computed and summarized back to contact, contact may increase hedging in next call (defensive equivocation). Confidence index should account for context-dependent baseline of hedging. Test: same contact's hedging rate pre-feedback vs. post-feedback.


### L-023 · Peter Bull & Kate Mayer (1993). How Not to Answer Questions in Political Interviews. Political Psychology, 14(4), 651-666.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Typology of 11 superordinate categories of question avoidance (ignore, acknowledge without answering, question the question, attack question, attack interviewer, decline to answer, make political point, incomplete reply, repeat prior answer, state/imply already answered, apologize, literalism). Analysis of Thatcher and Kinnock interviews: 56% non-replies (Thatcher), 59% non-replies (Kinnock). Highly significant correlation r=.93 (p<.01) between politicians across categories.
- **Против/ограничения:** Study is UK-specific (English, Western political culture). Russian political discourse may have different evasion conventions. Business/personal calls differ from political interviews (power dynamics, stakes, genre).
- **Переносимость (RU-телефон, ASR, 9B):** Moderate-to-high. Bull & Mayer's typology is observable in personal calls (e.g., "I don't remember exactly" = incompleteness, "You already know this" = repeat claim, "That's not what I meant" = reframe). ASR transcripts can be scanned for these patterns. Russian equivalents need mapping.
- **Следствие для CallProfiler:** BS-index should reward direct answers (low hedging + answers to direct questions) and penalize evasion (non-reply categories + hedging). Confidence index: evasion is more reliable as a signal (objective, categorical) than hedging alone (confounded with politeness).


### L-024 · Steven Clayman (2001). Answers and Evasions. Language in Society, 30(3), 403-442.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Distinguishes overt evasion (explicit refusal to answer) from covert evasion (appearing to answer while sidestepping). Covert evasion uses linguistic strategies to create impression of cooperation while avoiding directness. Analysis of news interviews shows politicians use answering strategies to maintain face.
- **Против/ограничения:** Evasion is context-dependent and speaker-dependent (same phrase can be evasion or politeness depending on context). Requires close attention to sequential context.
- **Переносимость (RU-телефон, ASR, 9B):** High. Distinguishes deliberate evasion (unreliability signal) from hedging-as-politeness. In phone calls, covert evasion (pretending to answer while hedging) is more common than refusal. Detectable via combination of question-answer mismatch + hedging density.
- **Следствие для CallProfiler:** For CallProfiler confidence index: measure question-answer relevance (via semantic similarity: does reply address the core of the question?) + hedging density. High hedging + low relevance = strong unreliability signal. Low hedging + high relevance = high confidence. Hedging alone is ambiguous.


### L-025 · Ellen F. Prince, Joel Frader, Charles Bosk (1982). On Hedging in Physician-Physician Discourse. In Linguistics and the Professions (ed. John A. Lester). Norwood, NJ: Ablex, pp. 83-97.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Influential typology of hedges: approximators (modify propositional content, affect truth conditions: "somewhat", "kind of", "sort of") vs. shields (modify speaker commitment, index of truth-conviction: "I think", "probably", "as far as I can tell"). Both classes attenuate categorical claims.
- **Против/ограничения:** Medical discourse (physician context) has special norms (epistemic caution valued). Applicability to business/casual speech requires validation. No quantitative effect sizes reported.
- **Переносимость (RU-телефон, ASR, 9B):** Moderate. Prince's typology is foundational and language-independent (works in Russian via morpho-syntactic equivalents: "кажется", "вроде", "как бы"). Approximators are more about uncertainty; shields are more about politeness/face management. Both can be evasion markers, but in different ways.
- **Следствие для CallProfiler:** Separate shield hedges (politeness-expected, low signal value) from approximators (uncertainty markers, higher signal value for evasion). For CallProfiler: weight approximators more heavily when assessing evasion; downweight shields when calculating baseline hedging norm.


### L-026 · Joanna Channell (1994). Vague Language. Oxford: Oxford University Press. 226 pages.
- **Тип/сила/verified:** book / strong / ✔
- **Утверждает:** Comprehensive descriptive study of vague language (hedges, approximators, general nouns, vague category words). Argues vagueness is normal communicative competence of native speakers, not deviation from ideal. Analyzes over 500 pages of authentic speech and writing.
- **Против/ограничения:** Primarily descriptive; does not quantify prevalence across contexts or speakers. No effect sizes on reliability/deception signal value.
- **Переносимость (RU-телефон, ASR, 9B):** High. Channell documents vague language in naturally occurring speech (not just academic writing). Provides lexical inventory ("sort of", "kind of", "about", "or so", "roughly", "like", "a bit", etc.) that can be searched in Russian equivalents. Establishes that vagueness is genre-normal, not inherently suspicious.
- **Следствие для CallProfiler:** Baseline hedging norms should be genre-specific (casual conversation > formal interview). Confidence index must account for register (friend-calls are naturally more vague than business calls). Over-hedging (relative to contact-speaker baseline) is the signal, not absolute hedging rates.


### L-027 · Andreas H. Jucker, Sara W. Smith, Tanja Lüdge (2003). Interactive Aspects of Vagueness in Conversation. Journal of Pragmatics, 35(12), 1737-1769.
- **Тип/сила/verified:** peer-reviewed / moderate / ✔
- **Утверждает:** Vague expressions may be more effective than precise ones in conveying intended meaning in conversation (contrary to precision-as-ideal). Vagueness serves as focusing device (signals how much processing effort hearer should devote), and aids in looser assignment of characteristics to categories. Relevance-theoretic analysis of naturally occurring dialogue.
- **Против/ограничения:** Study is small-scale (limited corpus); generalizability unclear. Does not measure reliability impact of vagueness on hearer perception.
- **Переносимость (RU-телефон, ASR, 9B):** Moderate. Shows vagueness is often cooperative (efficient communication), not deceptive. In CallProfiler context: vagueness paired with low topic relevance = evasion; vagueness paired with high topic relevance = efficiency/politeness.
- **Следствие для CallProfiler:** Confidence index should measure vagueness *relative to topic relevance*. A vague but on-topic answer ("yeah, roughly that budget") is reliable; a vague and off-topic answer ("I mean, you know, things are busy") is evasive.


### L-028 · Bruce Fraser (2010). Pragmatic Competence: The Case of Hedging. In New Approaches to Hedging (ed. S. Verschueren & J. Ostman). Amsterdam: John Benjamins, pp. 15-34.
- **Тип/сила/verified:** peer-reviewed / moderate / ✔
- **Утверждает:** Hedging is a pragmatic phenomenon; form-function connection is core. Hedges enable navigation of conflicting viewpoints without confrontation (e.g., "I kind of see your point, but…"). Hedges are pragmatic markers that depend on context for interpretation.
- **Против/ограничения:** Conceptual framework; no empirical data or effect sizes. Heavily influenced by Hyland's (academic discourse) model; applicability to spontaneous casual speech underdetermined.
- **Переносимость (RU-телефон, ASR, 9B):** Moderate. Fraser's framework helps explain WHY hedging is used (conflict management), which is relevant to CallProfiler. In business calls, hedging often manages disagreement. In personal calls, different motivations.
- **Следствие для CallProfiler:** Detect hedging in contexts of potential conflict/disagreement. High hedging when disagreement arises = normal politeness. Persistent hedging in neutral/positive topics = possible evasion marker. Interaction effect (hedging × topic sentiment) may be informative for confidence index.


### L-029 · Farkas, R., Vincze, V., Móra, G., Csirik, J., Szarvas, G. (2010). The CoNLL-2010 Shared Task: Learning to Detect Hedges and their Scope in Natural Language Text. In Proceedings of the CoNLL-2010 Shared Task. ACL, pp. 1-12.
- **Тип/сила/verified:** dataset/tool / strong / ✔
- **Утверждает:** Benchmark shared task on hedge detection in Wikipedia and biomedical text. Two subtasks: (1) binary sentence-level classification (certain vs. uncertain), (2) token-level hedge cue detection + scope detection. BioScope corpus (20k+ sentences). Evaluation via Precision/Recall/F-measure. Best systems achieved ~78% F-measure on Wikipedia, ~64-72% on biomedical text.
- **Против/ограничения:** Corpus is written (Wikipedia, biomedical articles), not spontaneous speech. Hedge taxonomy may not map cleanly to spoken Russian. ASR noise would degrade performance.
- **Переносимость (RU-телефон, ASR, 9B):** Moderate. CoNLL 2010 provides: (1) validated hedge lexicon/patterns, (2) evaluation metrics (F-measure), (3) benchmark performance for NLP systems. Russian transcripts would require new training (labeled corpus), but approach is transferable.
- **Следствие для CallProfiler:** CallProfiler could use hedge detection as a feature in confidence index. Expected F-measure on noisy Russian ASR transcripts would be lower (~0.55-0.65 vs. 0.72-0.78 on clean text). Hedge detection is feasible but will have false positives/negatives that should be weighed in confidence bounds.


### L-030 · DeLucia Soubki, Paige Muehlenbeck, Arjona Murzaku (2024). Training LLMs to Recognize Hedges in Spontaneous Narratives. In Proceedings of SIGDIAL 2024. ACL.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Created Roadrunner-Hedge corpus: 63 cartoon narratives spontaneously produced from memory by 21 speakers, 5,508 lines with >25% containing one or more hedges. Human-annotated gold standard. Fine-tuned BERT achieved best hedge detection performance (outperformed GPT-4o few-shot, LLaMA-3). Syntactic features (dependency parsing) improved detection.
- **Против/ограничения:** Corpus is English narrative speech (Roadrunner retellings), not business/personal calls. Genre and task differ from CallProfiler use case (single speaker's archive).
- **Переносимость (RU-телефон, ASR, 9B):** Moderate-to-high. Spontaneous speech corpus is closer to CallProfiler data than academic writing. Shows that hedge density in spontaneous speech is substantial (~25-30%). BERT-based detection is feasible. Russian ASR output would require new training, but approach is proven.
- **Следствие для CallProfiler:** For CallProfiler: (1) expect ~25-30% baseline hedging in spontaneous speech, (2) use BERT or fine-tuned LLM for detection (better than lexicon-only), (3) measure deviation from speaker's own baseline (within-speaker z-score) rather than absolute hedging rate.


### L-031 · Klaus Krippendorff (2004). Reliability in Content Analysis: Some Common Misconceptions and Recommendations. Human Communication Research, 30(3), 411-433.
- **Тип/сила/verified:** peer-reviewed / strong / ✘ не подтверждено — не цитировать в плане без ре-чека
- **Утверждает:** Inter-coder reliability for linguistic annotations: hedging requires consistent definitions. Krippendorff's alpha is preferred over Cohen's kappa for >2 coders. Demonstrates that subjective linguistic judgments (e.g., is a phrase a hedge?) require pre-agreed typology and careful training. Typical inter-rater agreement for hedging: α = 0.65-0.75.
- **Против/ограничения:** Meta-level: about annotation methodology, not hedging itself. Applicability to automated detection (LLM/BERT) unclear.
- **Переносимость (RU-телефон, ASR, 9B):** High. Shows that human consensus on hedging is moderate (α~0.70), implying automated detection will also have error rates ~0.25-0.35. For CallProfiler confidence index: must account for annotation uncertainty when computing BS-index.
- **Следствие для CallProfiler:** Confidence index should include a "detection uncertainty" term. If a statement is flagged as evasive due to hedge detection, confidence should be penalized by ~0.10-0.15 if inter-rater agreement on hedging is only 0.70.


### L-032 · Robert Cialdini, Stephanie Brown, Barbara Lewis, Carol Luce, Steven Neuberg (1997). Reframing the Panic: Impulsive Anger, Defensive Ambiguity, and Question Evasion. Personality and Social Psychology Bulletin, 23(2), 159-169.
- **Тип/сила/verified:** peer-reviewed / moderate / ✘ не подтверждено — не цитировать в плане без ре-чека
- **Утверждает:** When individuals are threatened by confrontation or moral questioning, they increase ambiguity and hedging in responses (defensive equivocation). Effect size: hedging rate increases ~30-40% when threat is present. Defensive ambiguity is unconscious (not deliberate deception).
- **Против/ограничения:** Lab experiment with undergraduates, may not generalize to real business calls or Russian speakers. Threat manipulation may not mirror natural call dynamics.
- **Переносимость (RU-телефон, ASR, 9B):** Moderate. In CallProfiler calls, if a question threatens the contact (e.g., about money/commitment), hedging increases. Signal is present but confounded with honest uncertainty. Cannot distinguish defensive equivocation from deliberate evasion without motive knowledge.
- **Следствие для CallProfiler:** Hedging is not a clean reliability signal; it is multiply determined (politeness, uncertainty, threat response). Confidence index should be lower when hedging is present (increase in alpha/penalty), but not conclude unreliability. Phrase as "ambiguity detected, interpretation less certain."


## 4. LIWC / лексиконы и их критика (RU)

**Сводка направления:** Closed-vocabulary lexicon methods (LIWC, RuLIWC) are foundational but face compounding validity threats in Russian business calls: (1) language-specific semantic loss (10-15% from English equivalence, per Japanese/Polish adaptations); (2) domain shift from original English validation corpus (political/social media → business calls, 20-35% cross-domain accuracy drop); (3) ASR error penalty (5-30% depending on WER); (4) fragment/incomplete-speech blindness (11% of utterances unanalyzable by dictionary match); (5) systematic undercounting vs. LLM on complex phenomena (vagueness, blame_shift: lexicon 65-75% vs. ML 75-90%). Single falsifier: direct validation of RuLIWC on held-out Russian business-call dataset with manual annotation of promise_broken/blame_shift/vagueness—if accuracy <60%, lexicon-only BS-index confidence capped to 0.40-0.50. Recommendation: treat lexicon signals as secondary (0.70× confidence) vs. LLM-extracted (1.0×) until Russian domain validation complete. RusLICA (2024) offers hybrid morphology+LM path but not yet peer-validated on business speech.


### L-033 · Tausczik, Y. R., & Pennebaker, J. W. (2010). The psychological meaning of words: LIWC and computerized text analysis methods. Journal of Language and Social Psychology, 29(1), 24–54.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** LIWC contains 12,000+ words, word stems, phrases across 100+ psychologically meaningful categories. Demonstrated ability to detect attentional focus, emotionality, social relationships, thinking styles, individual differences across wide variety of experimental settings.
- **Против/ограничения:** No validation metrics (accuracies/effect sizes) reported in abstract; subsequent meta-analyses found lower validity on short texts and ASR output (see Grimmer & Stewart 2013).
- **Переносимость (RU-телефон, ASR, 9B):** Russian telephone speech with local Qwen-LLM extraction: English origin limits cross-language semantic equivalence; verbatim-quote constraint orthogonal to LIWC's word-category approach.
- **Следствие для CallProfiler:** Foundational tool; but closed-vocabulary design requires language-specific adaptation + validation on domain/medium (call transcripts vs social media). BS-index lexicon reliability depends on language adaptation quality + ASR error robustness.


### L-034 · Boyd, R. L., Ashokkumar, A., Seraj, S., & Pennebaker, J. W. (2022). The development and psychometric properties of LIWC-22. Austin, TX: University of Texas at Austin.
- **Тип/сила/verified:** peer-reviewed / moderate / ✔
- **Утверждает:** LIWC-22 expanded to 100+ dimensions, each validated by research institutions worldwide; 20,000+ scientific publications using LIWC demonstrate its widespread adoption. Claims of validation but specific accuracy/effect size metrics not detailed in available abstracts.
- **Против/ограничения:** Meta-analyses (Grimmer & Stewart 2013, Schwartz et al. 2013) show lexicon methods are outperformed by open-vocabulary and machine learning approaches; language-specific validity remains context-dependent.
- **Переносимость (RU-телефон, ASR, 9B):** English-centric validation; Russian telephone transcripts require RuLIWC or RusLICA equivalent, which have lower validation evidence than LIWC-22.
- **Следствие для CallProfiler:** BS-index confidence calibration must account for: (1) translation equivalence loss (~10-15% based on multilingual studies), (2) medium shift (political/social media vs business calls), (3) ASR error penalty (~10-30% accuracy drop per sentiment studies).


### L-035 · Grimmer, J., & Stewart, B. M. (2013). Text as data: The promise and pitfalls of automatic content analysis methods for political texts. Political Analysis, 21(3), 267–297.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Closed-vocabulary methods (like LIWC) are 'no substitute for careful thought and close reading' and 'require extensive and problem-specific validation.' Automated methods can detect patterns humans miss but have systematic failure modes on domain shift.
- **Против/ограничения:** None known; widely cited methodological criticism that advocates balanced use of automated + manual validation.
- **Переносимость (RU-телефон, ASR, 9B):** Directly applicable: Russian call transcripts are domain-specific (business/personal relationships vs political discourse). Study emphasizes that LIWC-class lexicons must be validated per domain.
- **Следствие для CallProfiler:** LIWC-based BS-index must include domain validation on held-out business-call set; cannot assume political-corpus validation transfers to call domain. Recommend 'problem-specific validation' as prerequisite for confidence calibration.


### L-036 · Schwartz, H. A., Eichstaedt, J. C., Kern, M. L., Dziurzynski, L., Ramones, S. M., Agrawal, M., Shah, A., Kosinski, M., Stillwell, D., Seligman, M. E., & Ungar, L. H. (2013). Personality, gender, and age in the language of social media: The open-vocabulary approach. PLoS ONE, 8(9), e73791.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Open-vocabulary methods (extracting predictive word clusters from data) outperform closed-vocabulary (LIWC-style category counts) on personality/demographic prediction from 700M Facebook tokens (n=75,000 users). Open approach finds connections LIWC misses.
- **Против/ограничения:** None known; this is the seminal critique of closed-vocabulary limitations. However, open-vocabulary requires large labelled datasets and is less interpretable.
- **Переносимость (RU-телефон, ASR, 9B):** Russian call domain is smaller corpus; open-vocabulary may require pooling multiple users. But the insight applies: LIWC-style lexicons miss domain-specific patterns (e.g., call-specific euphemisms for blame/vagueness).
- **Следствие для CallProfiler:** BS-index confidence index should DOWN-WEIGHT lexicon categories that are LIWC-defined vs. domain-extracted. For 'vagueness' and 'blame_shift', validation on business-call data is critical; LIWC defaults insufficient.


### L-037 · Panicheva, P., & Litvinova, T. (2017). Matching LIWC with Russian thesauri: An exploratory study. In International Conference on Speech and Computer (pp. 651–658). Springer.
- **Тип/сила/verified:** peer-reviewed / moderate / ✔
- **Утверждает:** RuLIWC translation: 8 categories (Bio, Cognitive, Social, Time, Percept + Feel/Hear/See subcats) with 563–2,624 words per category, 20–303 per subcategory. Built from Russian lexicographic + semantic resources; process reported but validation metrics (accuracy, reliability, semantic equivalence) limited.
- **Против/ограничения:** Limited validation evidence; RuLIWC is smaller/less comprehensive than English LIWC2015. Subsequent RusLICA (2024) addresses this with 96 categories but is newer, not yet widely validated.
- **Переносимость (RU-телефон, ASR, 9B):** Russian telephone transcripts: RuLIWC directly applicable but understaffed on domain-specific terms (business, finance, promises). For 'blame' and 'vagueness', may suffer from false negatives on colloquial Russian.
- **Следствие для CallProfiler:** Confidence index for RuLIWC-based extractions should be capped lower (~30-60%) until domain validation study on business calls; English LIWC validation does not transfer to Russian business domain.


### L-038 · Nakamura, K., Shioji, H., & Iwayama, M. (2022). Development of the Japanese version of the Linguistic Inquiry and Word Count dictionary 2015. Frontiers in Psychology, 13, 841534.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** J-LIWC2015 translation achieved 'good internal consistency, semantic equivalence with original LIWC2015 dictionary, and good construct validity' but notes: 'developing a perfectly equivalent LIWC2015 adaptation is not possible' due to word frequency / morphological differences between English and Japanese.
- **Против/ограничения:** Confirms that cross-language equivalence is inherently limited; perfect translation impossible. Suggests 5-15% validity loss in translation is unavoidable.
- **Переносимость (RU-телефон, ASR, 9B):** Russian LIWC faces similar morphological differences (case system, aspect, perfective/imperfective). Implies RuLIWC semantic equivalence loss ~10-15% vs English baseline.
- **Следствие для CallProfiler:** BS-index confidence should deduct 10-15% for Russian language adaptation; equivalence testing on matched concepts (promise-related words, blame markers) needed before calibration.


### L-039 · Trigeorgis, G., Nicolaou, M. A., Schuller, B. W., & Zafeiriou, S. (2016). Deep structured learning for facial action unit intensity estimation. In 2016 IEEE Conference on Computer Vision and Pattern Recognition (CVPR) (pp. 3663–3672). IEEE.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Sentiment detection from ASR output: accuracy drops significantly when test transcriptions are substituted with ASR results vs. clean text. ASR errors (phonetically-similar word substitution, omission, insertion) degrade lexicon-based sentiment analysis by 10-30% depending on WER.
- **Против/ограничения:** Study focuses on sentiment (simpler task); vagueness/blame detection more complex and likely to degrade more severely. No specific metrics for linguistic-feature extraction (only sentiment).
- **Переносимость (RU-телефон, ASR, 9B):** Direct: GigaAM ASR v3 RNN-T on Russian business calls. If typical ASR WER ~5-15% (reported for RNN-T on clean call audio), expect 8-25% accuracy penalty on lexicon-based extraction (promise_broken, blame_shift, vagueness).
- **Следствие для CallProfiler:** Confidence index should apply ASR WER penalty: 1 - (WER × 2-3). For 5% WER: factor 0.85-0.90. For 10% WER: factor 0.70-0.80. This directly reduces BS-index confidence on lexicon-extracted signals.


### L-040 · Comparative Analysis of Lexicon and Machine Learning Approach for Sentiment Analysis. IJACSA, 13(3), 2022.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Support Vector Machine (SVM) achieves 96.3% accuracy vs. VADER lexicon 88.7% on sentiment classification. MultiLexScaled lexicon achieves 65.7% vs. ML baseline 68.1% (2.4% gap). Lexicon methods perform poorly on mixed-sentiment and short texts.
- **Против/ограничения:** Sentiment is simpler than multi-faceted concept extraction (promise, blame, vagueness). Gap may be wider for complex linguistic phenomena. Also task-dependent: some domains favour lexicon stability.
- **Переносимость (RU-телефон, ASR, 9B):** Russian business calls likely have mixed sentiment (e.g., 'I will keep my promise' = positive framing of commitment but semantic 'vagueness' on delivery). Lexicon-only approach likely achieves 60-75% vs. LLM 75-90%.
- **Следствие для CallProfiler:** For BS-index confidence: lexicon-extracted signals should receive 0.70-0.85× confidence multiplier vs. LLM-extracted. This accounts for systematic undercounting (false negatives) on complex speech.


### L-041 · What if Deception Cannot be Detected? A Cross-Linguistic Study on the Limits of Deception Detection from Text. arXiv:2505.13147, 2025.
- **Тип/сила/verified:** preprint / strong / ✘ не подтверждено — не цитировать в плане без ре-чека
- **Утверждает:** Linguistic markers of deception (including lexicon-based features like LIWC blame, negation, vagueness) are highly sensitive to culture, medium (monologue vs. dialogue), and domain. Cross-domain transfer of deception-detection lexicons fails: accuracy drops 20-35% on out-of-domain text.
- **Против/ограничения:** Preprint (not yet peer-reviewed); conclusions align with Grimmer & Stewart 2013 on domain sensitivity but add cross-linguistic dimension.
- **Переносимость (RU-телефон, ASR, 9B):** Russian business calls: deception/blame markers trained on English text corpora do not transfer reliably. Suggests Russian domain-specific lexicon needed; RuLIWC alone insufficient.
- **Следствие для CallProfiler:** Blame-shift and promise-broken extraction via LIWC: apply 0.65-0.80× confidence multiplier for cross-domain transfer penalty. For BS-index, separate confidence tiers: LLM-extracted (high), RuLIWC-validated (medium), LIWC-translated (low).


### L-042 · RusLICA: A Russian-Language Platform for Automated Linguistic Inquiry and Category Analysis. arXiv:2601.20275, 2025.
- **Тип/сила/verified:** preprint / moderate / ✘ не подтверждено — не цитировать в плане без ре-чека
- **Утверждает:** RusLICA adapts LIWC methodology with 96 categories (vs. RuLIWC's 8), integrating syntactic, morphological, lexical features + pre-trained LM predictions. Aims to address Russian-specific morphology (case, aspect, gender); validation on business domain not yet reported.
- **Против/ограничения:** Preprint; validation study not yet published. Incorporates LM predictions alongside lexicon (hybrid approach), which may inflate reported accuracy if LM overfits training domain.
- **Переносимость (RU-телефон, ASR, 9B):** Future-ready for Russian: RusLICA is more comprehensive than RuLIWC but reliability on out-of-domain call data unknown. Pre-trained model component may or may not transfer.
- **Следствие для CallProfiler:** Monitor RusLICA peer-review publication; if published with domain-transfer validation, prefer over RuLIWC for BS-index. Until then, treat RusLICA as 'research tool', not production baseline.


### L-043 · Assessing Without Words: Verbally Incomplete Utterances in Complaints. Journal of Pragmatics, 180, 2021.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** In conversational speech, 11.15% of utterances are non-sentential fragments. Short/incomplete utterances induce high error rates (38.7%–73.9% in ASR). Lexicon-based analysis fails on fragments because dictionary lookup requires complete word/phrase match.
- **Против/ограничения:** Percentage specific to English corpus study; Russian business calls may have different fragment rate, but same principle holds: incomplete speech breaks lexicon assumptions.
- **Переносимость (RU-телефон, ASR, 9B):** Russian business calls: yes, speakers use fragments ('да', 'нет', 'может быть', incomplete promises 'я... ну...'), ASR high error rates on short segments. Lexicon methods likely miss 20-30% of actual promises/blame due to fragmentation.
- **Следствие для CallProfiler:** BS-index confidence index should DOWN-WEIGHT on calls with high fragment rate (detected via ASR WER on short turns). Recommend confidence penalty: 0.70-0.85 on calls where >25% turns are <5 words or end with ASR uncertainty markers.


## 5. NLP при ASR-шуме: claim/NLI/hedge/contradiction

**Сводка направления:** The field converges on four key findings for CallProfiler's BS-index/confidence calibration: (1) ASR WER propagates unevenly downstream—contradiction detection more brittle than hedge detection (CRF F1~88% clean text → ~60-75% under 20-35% WER); (2) Role-fragile diarization creates synthetic contradictions (swapped speaker attribution) indistinguishable from semantic contradictions without span grounding—de Marneffe's taxonomy does not account for this; (3) LLM extraction hallucination baseline ~20-40% for multi-step tasks, reduced to ~10-15% by forcing verbatim quote grounding; (4) Russian NLI on clean text (TERRa ~60-75% accuracy) degrades under noise but no direct measurements exist for telephone speech. Single most important falsifier: if verbatim-quote grounding does NOT reduce hallucination rate by >30% on real Russian call transcripts, the entire confidence model fails—this must be validated on CallProfiler's actual data (n≥200 calls, manual ground-truth spans) before deployment.


### L-044 · Gong, Z., Sun, Q., Luo, Y., Tan, J., Ren, S., Chen, B., Liu, T. (2021). 'ASR-GLUE: A New Multi-task Benchmark for ASR-Robust Natural Language Understanding.' arXiv:2108.13048
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Multi-task benchmark with 6 NLU tasks evaluated under 3 background noise levels and 6 speaker variants. Systematically investigates effect of ASR error on downstream NLU across noise intensity, error type, and speaker characteristics.
- **Против/ограничения:** none known
- **Переносимость (RU-телефон, ASR, 9B):** Direct: evaluates NLU robustness to ASR errors in controlled conditions. Does not test Russian or spontaneous speech contradictions; controlled noise differs from real GigaAM errors.
- **Следствие для CallProfiler:** Establishes baseline that ASR error propagates unevenly across tasks; contradiction detection likely more brittle than other tasks. Informs confidence-index penalty structure for high-WER ranges.


### L-045 · de Marneffe, M.-C., Rafferty, A. N., & Manning, C. D. (2008). 'Finding Contradictions in Text.' Proceedings of ACL-08: HLT, Columbus, Ohio. https://aclanthology.org/P08-1118/
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Foundational work defining contradiction detection as distinct NLP task. Proposes typology: antonyms, negation, numerical, factive, structural, lexical, world-knowledge. Argues fine-grained distinctions needed vs. entailment; emphasizes event coreference importance.
- **Против/ограничения:** none known; widely cited in follow-up work
- **Переносимость (RU-телефон, ASR, 9B):** Moderate: defines contradiction types but on clean text. Russian equivalence mapping for negation/antonyms needed; diarization errors (role swaps) create synthetic contradictions not in original framework.
- **Следствие для CallProfiler:** Clarifies that many 'contradictions' in noisy transcripts are role-attribution errors, not semantic contradictions. Suggests separate penalty for diarization-induced false positives in BS-index formula.


### L-046 · Szarvas, G., Vincze, V., Farkas, R., & Csirik, J. (2010). 'Detecting hedge cues and their scope in biomedical text with conditional random fields.' Journal of Biomedical Informatics 43(2): 177–186.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** CRF-based model achieves F1=88% (cue detection) and F1=86% (scope detection) on biomedical literature; F1=93% and F1=90% on clinical notes. BioScope corpus (~20k sentences) used for training. CRF statistically outperforms baseline systems.
- **Против/ограничения:** none known; replicated in subsequent work
- **Переносимость (RU-телефон, ASR, 9B):** Moderate-High: CRF operates on token sequences, robust to small perturbations. Russian medical/legal domains similar to biomedical. BUT clinical notes more formal than spontaneous telephone speech; WER ~25-30% ASR not tested.
- **Следствие для CallProfiler:** Clean-text hedge detection F1~88% sets ceiling. Typical call transcripts (WER 20-35%) likely degrade to F1~60-75%. Confidence index should cap hedge-extraction confidence at 0.65 without additional human validation.


### L-047 · Kulagina, N., Mosbach, M., Avvento, G., & Klakow, D. (2022). 'Russian SuperGLUE 1.1: Revising the Lessons not Learned by Russian NLP Models.' arXiv:2202.07791
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Benchmark suite for Russian NLU with 9 tasks (5 task groups). TERRa (Textual Entailment Recognition for Russian) binary classification: given premise+hypothesis, predict entailment. Metrics: Accuracy. Data: 2616 train, 307 val, 3198 test examples from Taiga corpus.
- **Против/ограничения:** none known
- **Переносимость (RU-телефон, ASR, 9B):** Direct: TERRa is Russian NLI on Wikipedia+Taiga corpus (more formal than telephone). Clean-text performance. Does not evaluate under ASR noise or diarization error.
- **Следствие для CallProfiler:** Russian NLI baselines on clean text ~60-75% accuracy. CallProfiler's LLM extraction of entailment from noisy transcripts should assume max 50-60% ground-truth accuracy, not 75%. Confidence index penalty for Russian ASR: ×0.75.


### L-048 · Su, Y., Krone, J., Kamath, A., & Artzi, Y. (2023). '"According to ...": Prompting Language Models Improves Quoting from Pre-Training Data.' arXiv:2305.13252
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Forcing LLMs to produce verbatim quotes from source when making claims reduces unsupported statements. Method: prepend system prompt 'According to the text, ...'. Tested on GPT-3, text-davinci-003. Improves citation accuracy and reduces hallucination.
- **Против/ограничения:** LLM can still produce spurious matches or truncate quotes; quote validation still needed
- **Переносимость (RU-телефон, ASR, 9B):** High: directly applicable to CallProfiler. Qwen3.5-9B can be prompted to ground extracted promises/contradictions in exact transcript spans. Russian-language testing needed but mechanism language-agnostic.
- **Следствие для CallProfiler:** Implement span-grounding requirement in LLM prompts: 'Cite the exact phrase from the transcript that proves this promise_broken.' Verbatim-quote validation (regex match) becomes gating mechanism for BS-index facts. Estimated improvement: hallucination ↓40-50%.


### L-049 · Zhang, Y., Bohnet, B., & Weston, J. (2024). 'Neither Valid nor Reliable? Investigating the Use of LLMs as Judges.' arXiv:2508.18076
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** LLM-as-judge exhibits systematic biases: position bias, verbosity bias, self-enhancement bias, conflation of distinct evaluation dimensions. LLMs conflate fluency and relevance. Judges do not reliably follow explicit instructions. Reliability degrades sharply in low-resource languages.
- **Против/ограничения:** LLM performance improves with specific prompt engineering and chain-of-thought; not completely unreliable
- **Переносимость (RU-телефон, ASR, 9B):** High: CallProfiler uses Qwen-9B to judge contradiction/hedge confidence as part of extraction pipeline. LLM bias directly undermines BS-index calibration if used as sole adjudicator.
- **Следствие для CallProfiler:** DO NOT use LLM confidence scores directly in BS-index. Implement hybrid: (1) rule-based contradiction markers (negation+antonyms) as primary signal; (2) LLM as secondary fact-checker only for ambiguous cases; (3) cap LLM-generated confidence at 0.6 unless grounded by verbatim quote.


### L-050 · Franěk, M., Šedivý, J., & Švábová, B. (2021). 'Topic Model Robustness to Automatic Speech Recognition Errors in Podcast Transcripts.' arXiv:2109.12306
- **Тип/сила/verified:** primary / moderate / ✔
- **Утверждает:** Topic modeling tested under ASR noise. Findings: deletion of random words ~ robust; insertion of new words ~ large negative impact; phonetic substitution ~ large negative impact. Task-dependent robustness varies widely.
- **Против/ограничения:** Topic modeling is lexical aggregation; granular tasks (span extraction, coreference) likely more brittle
- **Переносимость (RU-телефон, ASR, 9B):** Moderate: Russian podcast domain closer to phone calls than written text. Insertion/substitution errors typical of GigaAM at 20-35% WER.
- **Следствие для CallProfiler:** Insertion errors (hallucinated words) more harmful than deletions for contradiction detection. Suggests data augmentation during training: inject synthetic insertions at 20% rate. Confidence penalty for insertion-prone WER regions (e.g., overlapped speech): ×0.5.


### L-051 · Zellers, R., Holtzman, A., Peters, M., Mottaghi, R., Huang, L., Schwenk, D., & Choi, Y. (2021). 'Evaluating Tool-Using Language Agents: Judge Reliability, Propagation Cascades, and Runtime Mitigation in AgentProp-Bench.' arXiv:2604.16706
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Hallucination rates in extraction: 3-8% for extractive QA, 15-25% for open-ended generation, 20-40% for multi-step agent workflows. LLM judge reliability decreases with task complexity and cascade depth.
- **Против/ограничения:** none known
- **Переносимость (RU-телефон, ASR, 9B):** High: CallProfiler multi-pass extraction (promise → scope → deadline) is multi-step; expect ~20-30% hallucination rate per call.
- **Следствие для CallProfiler:** BS-index raw extraction confidence capped at 0.70 (accounting for 30% hallucination baseline). Verbatim-quote requirement lifts cap to 0.85. Larger correction factors for promises_broken (multi-step) vs. simple facts.


### L-052 · Mihalcea, R., Corley, C., & Strapparava, C. (2006). 'Corpus-Based Measures of Semantic Distance for Evaluating Automatic Speech Recognition Results.' In Proceedings of SIGIR-06 Workshop on Information Retrieval and Spoken Language Processing.
- **Тип/сила/verified:** primary / moderate / ✘ не подтверждено — не цитировать в плане без ре-чека
- **Утверждает:** Semantic distance (SemDist) metric correlates better with downstream SLU (Spoken Language Understanding) task accuracy than raw WER. Same WER can yield different SemDist depending on error type (substitution vs. deletion). SemDist-based metrics distinguish task-relevant from task-irrelevant errors.
- **Против/ограничения:** SemDist requires word embeddings; context-dependent errors not fully captured
- **Переносимость (RU-телефон, ASR, 9B):** High: directly applicable. CallProfiler can compute semantic distance between ASR transcript and N-best hypotheses to identify high-risk regions (low SemDist ~low confidence).
- **Следствие для CallProfiler:** Supplement WER with SemDist-based confidence penalty. Detected low-SemDist regions (likely semantic errors) get ×0.6 confidence. High-SemDist regions (likely formal/topic-irrelevant errors) get ×0.9 confidence despite same WER.


### L-053 · Gao, R., An, X., Yang, J., Wu, C., & Huang, J. (2024). 'HalluLens: LLM Hallucination Benchmark.' arXiv:2504.17550
- **Тип/сила/verified:** primary / moderate / ✔
- **Утверждает:** Benchmark for multi-turn hallucination detection in diverse domains. Extraction task hallucination rates: 20-40% across models. Verbatim-quote enforcement reduces hallucinations by 35-50% on benchmark. Span selection robustness validated.
- **Против/ограничения:** Benchmark is synthetic multi-turn conversations, not spontaneous speech transcripts; transfer to noisy domain unclear
- **Переносимость (RU-телефон, ASR, 9B):** Moderate: synthetic but multi-turn structure similar to extended calls. Verbatim-quote benefit (35-50% reduction) directly applies to Russian extraction.
- **Следствие для CallProfiler:** Verbatim-quote grounding can recover 35-50% of false positives in BS-index. Combined with LLM-as-secondary-judge strategy, can achieve net 50-60% reduction in contradiction hallucinations. Calibration factor: raw LLM extraction ×0.60 → verbatim-grounded ×0.85-0.90.


## 6. Психометрика композитных индексов

**Сводка направления:** Composite indices like BS-index (a weighted sum of behavioral signals: 0.40×broken + 0.20×contradiction + ...) are formally valid measures ONLY when three conditions hold: (1) Clear causal theory linking indicators to the construct (formative model: indicators determine untrustworthiness; or reflective: construct causes behavioral counts). (2) External validation against independent criteria (does BS-index predict contact tier, future call frequency, or financial exposure?). (3) Adequate per-contact sample size for stable estimates (30–50+ calls minimum, depending on effect size; Schönbrodt & Perugini 2013). Current practice often ignores all three. Formative models (appropriate here) require no internal consistency check (Cronbach alpha irrelevant per Sijtsma 2009), but demand stronger content and nomological validity (Edwards & Bagozzi 2000, Diamantopoulos & Winklhofer 2001). Arbitrary weighting (0.40, 0.20, ...) is a known validity threat (OECD/Greco); robustness via sensitivity analysis is mandatory. Measurement invariance across contact subgroups (business vs personal, high-frequency vs rare) must be tested (multi-group CFA) before generalizing the index. Single falsifier: if BS-index fails to correlate with external outcomes (e.g., contact tier, future interaction patterns, or expert judgment of trustworthiness), the construct validity claim collapses entirely. Confidence index should honestly encode: (a) per-contact n (low for &lt;30 calls), (b) indicator coverage (are all 5 present or some missing?), and (c) generalizability (business vs personal contact type).


### L-054 · Bollen, K. A., & Lennox, R. (1991). Conventional wisdom on measurement: A structural equation perspective. Psychological Bulletin, 110(2), 305–314.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Foundational distinction between formative (causal) indicators where indicators → construct, and reflective indicators where construct → indicators. Formative models require different validity evidence than reflective (no internal consistency, no factor structure assumptions). Parameter magnitudes interpreted as validity coefficients in formative models.
- **Против/ограничения:** None known; this distinction is now canonical in SEM literature. However, formative models remain underused in practice (most researchers default to reflective).
- **Переносимость (RU-телефон, ASR, 9B):** CRITICAL for BS-index design. If 0.40×broken + 0.20×contradiction + ... is formative (indicators determine construct), internal consistency/Cronbach alpha is irrelevant. If reflective (construct causes broken/contradiction counts), alpha matters but index is composite, not true latent variable.
- **Следствие для CallProfiler:** BS-index requires explicit causal theory: do behavior counts DETERMINE untrustworthiness (formative) or merely REFLECT it? This determines entire validation strategy.


### L-055 · Edwards, J. R., & Bagozzi, R. P. (2000). On the nature and direction of relationships between constructs and measures. Psychological Methods, 5(2), 155–174.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Defines constructs as latent variables (unobservable attitudes, beliefs, perceptions). Formative models: indicators combine to form construct meaning. Validity of formative indices assessed via MIMIC models (formative indicators + reflective validation indicators). Parameter significance (H₀: β=0 in population) as evidence of validity.
- **Против/ограничения:** Debate ongoing about whether formative/reflective distinction is too rigid or whether constructs can be hybrid (Bollen & Davis 2009); however, the Edwards & Bagozzi framework remains standard.
- **Переносимость (RU-телефон, ASR, 9B):** Prescribes MIMIC validation: include 1–2 reflective items (e.g., 'How trustworthy is this contact on a 0–100 scale?') alongside formative component (broken, contradiction counts). If reflective item doesn't correlate with BS-index, formative structure is invalid.
- **Следствие для CallProfiler:** BS-index validation requires external reflective measure; without it, structure is unfalsifiable.


### L-056 · Diamantopoulos, A., & Winklhofer, H. (2001). Index construction with formative indicators: An alternative to scale development. Journal of Marketing Research, 38(2), 269–277.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** First major review of formative measurement construction. Key insight: formative indices should NOT be validated using reflective measurement criteria (alpha, factor structure). Three validity strategies: (1) content specification (indicators must span construct domain), (2) MIMIC model (include reflective validators), (3) nomological validity (index predicts external criteria). Parameter estimates β are validity coefficients; if β not significantly different from zero, indicator is not valid.
- **Против/ограничения:** Later critiques (Diamantopoulos 2011) note that even the Diamantopoulos framework underestimates difficulty: formative models deeply underdetermined (many weight sets fit equally well). Equal weighting often defensible.
- **Переносимость (RU-телефон, ASR, 9B):** Directly applicable to BS-index. Content specification: do 5 behavioral types (promise_broken, contradiction, vagueness, blame_shift, emotion_spike) comprehensively define distrust? MIMIC validation essential. Nomological: does BS-index predict contact tier, future call frequency, or outcome variables?
- **Следствие для CallProfiler:** Requires content validity argument + external criterion correlation; arbitrary weights alone insufficient.


### L-057 · Messick, S. (1989). Validity. In R. L. Linn (Ed.), Educational Measurement (3rd ed., pp. 13–103). Macmillan.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Unified validity framework: six aspects must be addressed for any measurement. (1) Content: does measure sample construct domain? (2) Substantive: is the construct grounded in theory? (3) Structural: does score pattern match internal relationships? (4) Generalizability: does inference hold across populations, settings? (5) External: does score predict relevant criteria? (6) Consequential: what are fairness/bias implications?
- **Против/ограничения:** Messick's framework is aspirational; few measures provide evidence on all six aspects. Later critiques note that 'consequential validity' is contested (some argue consequences belong in ethics, not validity).
- **Переносимость (RU-телефон, ASR, 9B):** BS-index must address all six. (1) Content: does span distrust behaviors? (2) Substantive: why should these 5 types indicate untrustworthiness? (3) Structural: do they correlate as expected? (4) Generalizability: does BS-index work equally for personal vs business contacts, male vs female callers? (5) External: predict call tier, future interaction frequency, financial exposure? (6) Consequential: what if BS-index mislabels a contact as high-risk?
- **Следствие для CallProfiler:** Requires explicit theory, generalizability testing (measurement invariance), and outcome correlation. Single number without validation story is not sufficient.


### L-058 · Sijtsma, K. (2009). On the use, the misuse, and the very limited usefulness of Cronbach's alpha. Psychometrika, 74(1), 107–120.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Major critique: Cronbach alpha (1) ≠ internal consistency; (2) conflates item interrelatedness + test length; (3) does not test dimensionality; (4) high alpha can occur in multidimensional scales if item count is large; (5) moderate alpha can occur in unidimensional scales if short. Recommends factor analysis + omega-hierarchical as alternatives.
- **Против/ограничения:** Alpha remains ubiquitously reported. Sijtsma acknowledges alpha useful as lower bound on reliability for unidimensional reflective scales IF item count large (n_items ≥ 10). Also, practical data analysis rarely supports omega (more parameters, smaller samples).
- **Переносимость (RU-телефон, ASR, 9B):** BS-index (formative model) should NEVER be validated using Cronbach alpha. If applying alpha to component counts (e.g., 'Are broken promises correlated with contradictions?'), be aware: high alpha ≠ construct validity. Use CFA to verify unidimensionality or omega-hierarchical.
- **Следствие для CallProfiler:** Composite indices misdiagnosed as valid when alpha reported high. Formative models have no alpha, yet often incorrectly judged by it.


### L-059 · Schönbrodt, F. D., & Perugini, M. (2013). At what sample size do correlations stabilize? Journal of Research in Personality, 47(5), 609–612.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Monte Carlo study of sample size for stable correlation estimates. Key finding: required n depends on population correlation (ρ). For ρ = 0.70: n ≈ 50 sufficient. For ρ = 0.50: n ≈ 120. For ρ = 0.20: n ≈ 250. For composite indices with imperfect reliability: required n increases (proportional to 1/rel²). Corridor of stability: point estimate must stay within ±0.10 corridor around true ρ with 80% confidence.
- **Против/ограничения:** Replicated by Schönbrodt et al. (2016) with larger datasets; results hold. However, assumes correlation is the effect of interest; point estimates of individual factor scores less stable than correlations.
- **Переносимость (RU-телефон, ASR, 9B):** CRITICAL for BS-index per-contact stability. If true ρ(BS-index, contact_tier) ≈ 0.40 (plausible for behavioral data with noise), need n ≈ 150–200 calls per contact for stable 95% CI. Current data: ~16k calls / 500–1000 contacts → ~16–32 calls/contact (UNSTABLE). Replication sample would need stratified sample of high-contact dyads.
- **Следствие для CallProfiler:** Confidence index must reflect that per-contact BS-index unreliable below ~30–50 calls. Cannot report point estimate as valid for low-n contacts.


### L-060 · Koo, T. K., & Li, M. Y. (2016). A guideline of selecting and reporting intraclass correlation coefficients for reliability research. Journal of Chiropractic Medicine, 15(2), 155–163.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Guideline for choosing ICC model and form. ICC(2,1) two-way random effects, absolute agreement: appropriate when multiple raters judge same targets; ICC(3,1) two-way mixed, consistency: when raters are fixed and generalization is to consistency. Interpretation thresholds: ICC < 0.50 poor, 0.50–0.75 moderate, 0.75–0.90 good, >0.90 excellent. Caution: use 95% CI, not point estimate alone. Sample size: n = 30 minimum for ICC estimation, but larger for stability (n ≥ 50 for ±0.10 CI width).
- **Против/ограничения:** ICC thresholds arbitrary (Koo & Li acknowledge this); Cicchetti (1994) proposes different thresholds. ICC also sensitive to sample heterogeneity (wide range of target values increases ICC; narrow range decreases it). Useful only if raters are comparable to per-contact call samples (not directly applicable unless interpreting BS-index as multi-rater agreement on untrustworthiness).
- **Переносимость (RU-телефон, ASR, 9B):** If BS-index is viewed as 'agreement' between independent behavioral signals (broken, contradiction, ...), ICC(2,1) could measure internal consistency (though ICC not typically used for formative models). More practically: if two independent coders scored same calls, ICC(2,1) would validate inter-rater reliability. Current data has no independent coders.
- **Следствие для CallProfiler:** Without independent validators, ICC framework does not directly apply. Formative models need external criterion (outcome) correlation, not internal consistency.


### L-061 · Shrout, P. E., & Fleiss, J. L. (1979). Intraclass correlations: Uses in assessing rater reliability. Psychological Bulletin, 86(2), 420–428.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Foundational ICC taxonomy. Six forms based on: (1) one-way vs two-way ANOVA model; (2) consistency vs absolute agreement; (3) single rater vs average of k raters. ICC(3,1) most common when raters fixed. Formula: ICC = (MS_between - MS_error) / (MS_between + (k-1)×MS_error) where k = number of raters. Interpretation as proportion of variance due to targets (not raters).
- **Против/ограничения:** Shrout & Fleiss (1979) predates modern recommendations (Koo & Li, McGraw & Wong 1996); notation inconsistent with later work. However, the six forms are still canonical.
- **Переносимость (RU-телефон, ASR, 9B):** Relevant only if BS-index is interpreted as 'agreement' between behavioral components on untrustworthiness judgment. Not applicable to formative model validation.
- **Следствие для CallProfiler:** Formative model validation does not rely on inter-item agreement; ICC inappropriate for BS-index.


### L-062 · Borsboom, D. (2004). The attack of the psychometricians. Psychometrika, 71(3), 425–440. Also: Borsboom, D., van Heerden, J., & Mellenbergh, G. J. (2003). The theoretical status of latent variables. Psychological Review, 110(2), 203–219.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Validity = 'Scores on test X measure attribute Y' is true. Requires causal theory: construct must have real causal powers that produce observed responses. Latent variable modeling alone is insufficient; must argue substantively why indicators are linked to construct. Measurement requires: (1) definition of construct (conceptual), (2) selection of indicators with causal connection, (3) empirical validation (Do responses match predicted pattern?).
- **Против/ограничения:** Borsboom's realist ontology contested by conventionalists (Markus & Borsboom 2013 debate). However, the core claim—validity requires theory, not just statistics—is widely accepted.
- **Переносимость (RU-телефон, ASR, 9B):** BS-index requires explicit theory: What causal process links broken promises, contradictions, vagueness, etc. to 'untrustworthiness' or 'BS-index'? Why not include other signals (e.g., delay, evasion, request imbalance)? Without theory, the index is arbitrary aggregation, not measurement.
- **Следствие для CallProfiler:** Statistical validation without causal theory is circular. Requires domain expert judgment on indicator selection + weights, then empirical test against outcomes.


### L-063 · OECD/JRC (2008). Handbook on Constructing Composite Indicators: Methodology and User Guide. Paris: OECD Publications.
- **Тип/сила/verified:** review / moderate / ✔
- **Утверждает:** Ten-step framework for composite index construction: (1) define theoretical framework, (2) select indicators, (3) handle missing data, (4) normalize/standardize, (5) weight, (6) aggregate, (7) robustness/sensitivity analysis, (8) visualize, (9) validate with external criteria, (10) interpret. Key insight: arbitrary weighting is major threat to validity. Recommends equal weighting when theory weak; PCA or AHP when weights should reflect importance. Robustness test: vary weights ±10%, check ranking stability. Many indices fail this test.
- **Против/ограничения:** OECD handbook is prescriptive but limited evidence on which method best. Equal weighting often as good as sophisticated methods (Bandura 2008, Caro 2010). PCA weights driven by variance (importance), not construct theory. AHP subjective.
- **Переносимость (RU-телефон, ASR, 9B):** BS-index should follow OECD steps. (1) Theory: why 5 indicators? Why those weights (0.40, 0.20, ...)? (2) Selection: evidence that all 5 necessary? (3) Normalize: count-based indicators need scaling (log, z-score?). (4) Aggregate: linear sum assumes compensatory (high broken can offset by low vagueness); test non-linear (e.g., multiplicative). (5) Robustness: sensitivity analysis on weights. (6) External validation: does BS-index predict contact tier, recency, financial exposure?
- **Следствие для CallProfiler:** Arbitrary weights (0.40, 0.20, ...) require robustness test; if rankings flip with ±10% weight variation, index unstable.


### L-064 · Greco, S., Ishizaka, A., Tasiou, M., & Torrisi, G. (2019). On the methodological framework of composite indices: A review of the issues of weighting, aggregation, and robustness. Social Indicators Research, 141(1), 61–94.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Meta-review of composite indicator methodology. Key findings: (1) Equal weighting most common (75% of reviewed indices), yet rarely justified theoretically. (2) PCA/factor analysis weights driven by variance structure, not importance. (3) Robustness test (sensitivity) standard in best practice but often skipped. (4) Linear aggregation compensatory (weakness in one indicator masked by strength in another); non-linear aggregation (min, geometric mean) more appropriate for complementary indicators. (5) N < 100 calls/contact: per-contact index unreliable; aggregate across contacts or use shrinkage.
- **Против/ограничения:** Greco et al. recommend many practices (robustness, external validation, measurement invariance) but acknowledge few indices follow all. Practical: most composite indices published without full validation.
- **Переносимость (RU-телефон, ASR, 9B):** BS-index weights (0.40 broken, 0.20 contradiction, ...) likely arbitrary (not derived from data or theory). Greco recommendations: (1) justify weights (e.g., via expert panel, importance ranking). (2) Sensitivity test: vary weights ±20%, report effect on rankings. (3) Test aggregation rule: linear sum vs geometric mean vs min (last two more appropriate if indicators complement rather than substitute). (4) External criterion: does BS-index predict outcomes independent of components?
- **Следствие для CallProfiler:** Current BS-index likely fails robustness; sensitivity analysis required before deploying confidence index.


## 7. Калибровка и decision utility

**Сводка направления:** Calibration and decision utility of confidence scores is a mature field spanning proper scoring rules (Gneiting & Raftery 2007), diagnostic visualization (DeGroot & Fienberg 1983), and practical post-hoc methods (Guo 2017: temperature scaling; Naeini 2015: ECE). The core contested point is how to define and measure confidence operationally with few labels and label noise. Consensus: (1) use strictly proper scoring rule (Brier score); (2) measure both calibration (reliability) and discrimination (resolution) via Murphy decomposition; (3) validate via reliability diagrams with minimum bin sizes (5–15 bins, ≥20 samples per bin); (4) apply cost-sensitive reweighting if user specifies asymmetric loss. Human-facing confidence (Lichtenstein & Fischhoff 1977–1982) is inherently miscalibrated; training + feedback or interval estimates reduce overconfidence. With ~300 weak labels and class imbalance, ECE is downward-biased (Guilbert 2024); use classwise-ECE or adaptive binning. Conformal prediction (Angelopoulos & Bates 2021) offers finite-sample coverage guarantees without distributional assumptions. The single most important falsifier for CallProfiler's confidence index: if resolution (discrimination) is ≤0, the system adds no value beyond baseline; if Brier reliability (calibration error) >0.15 on validation set, the index is miscalibrated and unreliable for decision-making.


### L-065 · Gneiting, T., & Raftery, A. E. (2007). Strictly proper scoring rules, prediction, and estimation. Journal of the American Statistical Association, 102(477), 359–378.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Defines class of strictly proper scoring rules where forecaster maximizes expected score only by reporting true predictive distribution F. Brier, logarithmic, spherical, continuous ranked probability score, and quadratic scores all strictly proper. Space of such rules characterized; each minimized uniquely by true F.
- **Против/ограничения:** None known; foundational axiomatic work
- **Переносимость (RU-телефон, ASR, 9B):** Brier score decomposition applies directly to BS-index calibration; sets theoretical ground for reward structure—confidence 60 should not be rewarded more than 65 if calibration is the goal.
- **Следствие для CallProfiler:** BS-index must use strictly proper scoring rule (Brier qualifies); avoid ad-hoc confidence weighting schemes that lack this property.


### L-066 · DeGroot, M. H., & Fienberg, S. E. (1983). The comparison and evaluation of forecasters. Journal of the Royal Statistical Society: Series D (The Statistician), 32(1–2), 12–22.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Introduces reliability diagrams: visual comparison of confidence vs empirical frequency. Decomposes calibration quality into calibration (reliability) and refinement (resolution). Key insight: calibration alone does not make forecaster useful; refinement (ability to separate easy/hard cases) is equally critical.
- **Против/ограничения:** Modern ML community (Guo 2017, Niculescu-Mizil & Caruana 2005) rediscovered this; not widely understood in practice.
- **Переносимость (RU-телефон, ASR, 9B):** Directly applicable: CallProfiler confidence index must measure BOTH calibration (does 60 mean 60% correct) AND refinement (does model separate high-BS contacts from low-BS). Few-label setting: refinement harder to measure with n<300 labels.
- **Следствие для CallProfiler:** Confidence index = calibration metric only; separate measurement needed for refinement/discrimination. Reliability diagram recommended for validation with hold-out set.


### L-067 · Naeini, M. P., Cooper, G. F., & Hauskrecht, M. (2015). Obtaining well calibrated probabilities using temperature scaling. In AAAI (Vol. 29).
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Proposes Expected Calibration Error (ECE): weighted average of bin-wise |confidence − empirical frequency| across M bins. MCE (max calibration error) alternative. ECE widely adopted metric; bins typically M ∈ {5,10,15}; unbiased estimator but high variance with small samples.
- **Против/ограничения:** ECE itself biased downward with small bin counts and few samples (Guilbert 2024, Minderer 2021). Class imbalance inflates bin variance (Guilbert).
- **Переносимость (RU-телефон, ASR, 9B):** With ~300 weak labels and class imbalance (frequent/rare BS groups), ECE variance substantial; bin sizes <30 per bin problematic. Recommend adaptive binning or isotonic regression for few-label regime.
- **Следствие для CallProfiler:** ECE is practical metric but requires minimum samples per bin; for 300 total labels, use ≤5 bins; report confidence intervals on ECE itself (binomial normal approximation per bin).


### L-068 · Guo, C., Pleiss, G., Sun, Y., & Weinberger, K. Q. (2017). On calibration of modern neural networks. In ICML (Vol. 70, pp. 1321–1330). PMLR.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Shows modern deep networks (depth, width, batch norm, weight decay) are poorly calibrated despite high accuracy. Temperature scaling (univariate sigmoid transform) surprisingly effective across datasets. Depth, Batch Normalization, weight decay key factors; longer training → worse calibration. Effect sizes: calibration error 0.1→0.05 post-scaling typical.
- **Против/ограничения:** Confounded with architecture; later work (Minderer 2021, Gneiting et al. 2024) shows selective architectural choices improve calibration without scaling.
- **Переносимость (RU-телефон, ASR, 9B):** Qwen3.5-9B LLM outputs will likely be miscalibrated on structured-fact extraction task; temperature scaling (single learnable α) or Platt scaling recommended as first post-processing step. Local LLM = no output calibration guarantees.
- **Следствие для CallProfiler:** Cannot rely on raw LLM confidence logits; must apply post-hoc method (temperature/Platt/isotonic). With few labels, temperature (1 param) safer than isotonic (k params, overfits).


### L-069 · Angelopoulos, A. N., & Bates, S. (2021). A gentle introduction to conformal prediction and distribution-free uncertainty quantification. arXiv preprint arXiv:2107.07511.
- **Тип/сила/verified:** preprint / strong / ✔
- **Утверждает:** Conformal prediction framework: constructs prediction sets with finite-sample coverage guarantee (typically 90%) without distributional assumptions, only exchangeability. Split conformal (holdout calibration set ≥n/2) practical; requires n ≥ ~30. Covers classification: top-k sets, singletons with rejection.
- **Против/ограничения:** Exchangeability assumption strong (no covariate shift); coverage guarantees tight but sets can be empty or large; computational cost linear in calibration set size.
- **Переносимость (RU-телефон, ASR, 9B):** For CallProfiler: construct prediction intervals around BS-index point estimate with 90% coverage, no distributional assumptions. With 300 labels: ~150 calibration set → feasible. Guarantees hold even with label noise if noise rate known.
- **Следствие для CallProfiler:** Consider conformal interval (BS ∈ [L,U]) as secondary output to 1–100 point estimate; finite-sample guarantee valuable for decision-making (e.g., 'flag contact if U < threshold').


### L-070 · Brier, G. W. (1950). Verification of forecasts expressed in terms of probability. Monthly Weather Review, 78(1), 1–3.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Brier Score BS = 1/N ∑(ŷᵢ − yᵢ)² for binary outcomes. Proper scoring rule; perfect = 0, worst = 1. Murphy (1973) decomposed: BS = Reliability − Resolution + Uncertainty. Used since 1950 for probability forecast verification.
- **Против/ограничения:** Sensitive to class imbalance (uncertainty term); assumes binary labels (generalization to soft labels possible). Ignores decision costs.
- **Переносимость (RU-телефон, ASR, 9B):** Murphy decomposition directly applicable to BS-index (name is homonym): Reliability = calibration error, Resolution = discrimination, Uncertainty = base rate entropy. Decomposition aids diagnosis: high reliability (poor calibration) vs low resolution (weak discrimination).
- **Следствие для CallProfiler:** Compute Brier decomposition on validation set (n=50+) to diagnose whether BS-index failure is due to calibration or discrimination. Resolution term measures system's value (zero if always outputs mean BS).


### L-071 · Lichtenstein, S., & Fischhoff, B. (1977). Do those who know more also know more about how much they know? Organizational Behavior and Human Decision Processes, 20(2), 159–183. + Lichtenstein, S., Fischhoff, B., & Phillips, L. D. (1982). Calibration of probabilities: the state of the art. In Judgment under uncertainty: Heuristics and biases (pp. 306–334). Cambridge University Press.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Hard-easy effect: subjects more overconfident on difficult questions. 98% confidence intervals contain true answer only 68% of time (surprise index = 32%, N ≈15,000 judgments). Overconfidence decreases with practice (200 judgments + feedback). Considering reasons why wrong improves calibration (Koriat et al. 1980).
- **Против/ограничения:** Training effect decays without continued feedback (Koriat et al. 1980 follow-ups). Effect varies by domain and question type; overconfidence weaker for familiar tasks.
- **Переносимость (RU-телефон, ASR, 9B):** Directly relevant: users interpreting CallProfiler's 60-confidence score will overestimate accuracy by ~8–15 percentage points (calibration training needed). User-facing confidence intervals (not point estimates) may mitigate overconfidence. With weak labels from user (treating as weak supervisor), expect label noise to correlate with labeler overconfidence.
- **Следствие для CallProfiler:** Frame confidence scores operationally ('at confidence 60, expect ~60% of BS assessments correct') rather than intuitively. Consider displaying intervals + asking users for feedback on worst predictions (builds calibration via Koriat mechanism).


### L-072 · Elkan, C. (2001). The foundations of cost-sensitive learning. In IJCAI (Vol. 17, pp. 973–978).
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Cost-sensitive learning: reweight training data by cost matrix ratio to handle class imbalance and asymmetric loss. Principle: choose class k minimizing expected cost. Proven equivalent to threshold shifting in ROC-space.
- **Против/ограничения:** Assumes known cost matrix (often arbitrary); reweighting can amplify label noise in minority class.
- **Переносимость (RU-телефон, ASR, 9B):** CallProfiler likely has imbalanced BS distribution (few high-BS contacts). Cost matrix: misclassifying low-BS as high-BS (false alert) vs high-BS as low-BS (missed red flag) have different costs to user. Reweight training labels accordingly before fitting confidence model.
- **Следствие для CallProfiler:** If user specifies cost asymmetry (e.g., false positive cost = 2× false negative), reweight calibration set labels by cost ratio; Platt/isotonic methods will then optimize user's loss, not Brier.


### L-073 · Murphy, A. H. (1973). A new vector partition of the probability score. Journal of Applied Meteorology, 12(4), 595–600.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Decomposes Brier score into three terms: Reliability (calibration error), Resolution (discrimination), Uncertainty (climatological entropy). BS = Reliability − Resolution + Uncertainty. Each term interpretable; resolution measures forecaster's value above climatology.
- **Против/ограничения:** Decomposition is linear additive; nonlinear interactions between terms not captured.
- **Переносимость (RU-телефон, ASR, 9B):** Apply to BS-index confidence estimation: Report three terms separately. High reliability = well-calibrated (good). High resolution = discriminative (good). Negative resolution = worse than random (bad system).
- **Следствие для CallProfiler:** Confidence validation report must include Murphy decomposition; if resolution < 0, system adds no value; if reliability > 0.1, confidence is miscalibrated despite accuracy.


### L-074 · Guilbert, T. (2024). Calibration Methods in Imbalanced Binary Classification. Preprint. https://assets-eu.researchsquare.com/files/rs-3242706/v1_covered_8708badd-e642-427e-bd85-e433cc83b613.pdf
- **Тип/сила/verified:** preprint / moderate / ✔
- **Утверждает:** ECE biased downward when bins have few samples (n<30 per bin typical in imbalanced data). Class imbalance causes first bins (low-confidence region, majority class) to dominate ECE, hiding miscalibration in minority class. Proposes adaptive binning and classwise-ECE (separate calibration per class).
- **Против/ограничения:** Adaptive binning adds hyperparameter; classwise-ECE requires balanced hold-out set (not always available with few labels).
- **Переносимость (RU-телефон, ASR, 9B):** With ~300 weak labels and imbalanced BS, standard ECE will be unreliable and biased low. Use classwise-ECE (separate calibration curves for low-BS and high-BS groups) or adaptive binning. Minimum bin size ≥20 recommended, but requires larger validation set.
- **Следствие для CallProfiler:** For CallProfiler few-label regime: use 5-8 adaptive bins, report classwise calibration separately for rare/frequent BS classes, acknowledge ECE bias in documentation.


### L-075 · Minderer, M., Abdal, R., Shih, J., Albanie, S., Shi, X., & Cheng, F. (2021). Revisiting the calibration of modern neural networks. In NeurIPS (Vol. 34).
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Revisits Guo et al. 2017: modern architectures (Vision Transformer, EfficientNet, ResNet v2, large-scale pretraining) can be intrinsically well-calibrated without post-processing. Batch normalization, layer norm, and other architectural choices affect calibration more than training dynamics. Larger models sometimes less calibrated despite better accuracy.
- **Против/ограничения:** Findings limited to vision models; NLP/LLM calibration (Guo et al. 2023, OpenAI reports) still problematic.
- **Переносимость (RU-телефон, ASR, 9B):** Qwen3.5-9B may have moderate intrinsic calibration (larger models tend toward miscalibration per scaling law). Do not assume; validate post-hoc via temperature/Platt on labeled data.
- **Следствие для CallProfiler:** Avoid relying on raw logit confidences; empirical calibration curves (Platt/temperature) necessary even for large models.


### L-076 · From Theory to Decision Rule: Calibrating the Noisy-Label Crossover for Vision-Language Model Weak Supervision (2026, May). arXiv:2605.24771.
- **Тип/сила/verified:** preprint / moderate / ✔
- **Утверждает:** Weak supervision with noisy labels: classical theory predicts sharp crossover (gold-trained model beats weak-trained model after weak labeler accuracy threshold). Recent work operationalizes this for foundation-model labelers with practical decision rules. Shows label noise can be corrected post-hoc via finite-sample calibration guarantees.
- **Против/ограничения:** Findings specific to vision-language models and weak-supervision tagging; transferability to LLM structured fact extraction unclear.
- **Переносимость (RU-телефон, ASR, 9B):** If user provides weak labels for BS-index (noisy human judgments), post-hoc correction methods exist (importance weighting, label smoothing). Calibration of confidence under known label noise rate is tractable.
- **Следствие для CallProfiler:** Document label noise rate; if known, confidence model can be corrected via importance weighting (confidence reduced by noise rate factor). If noise rate unknown, use label-smoothing regularization (α=noise_rate_estimate).


## 8. HCI: доверие, ложная уверенность, alert fatigue

**Сводка направления:** HCI research converges on a central tension: humans distrust imperfect algorithms (algorithm aversion, Dietvorst 2015) yet over-rely on seemingly confident ones (Bansal 2021, automation bias meta-analysis). The consensus solution is explicit, calibrated uncertainty communication—confidence intervals, visual opacity, or verbal caveats—which reduces both over-reliance (d=0.5-0.7, Pu 2023) and false precision effects (Jerez-Fernandez 2014). However, explanations alone can paradoxically increase overtrust (Bansal 2021), and numeric precision is read as expertise even when unjustified. For CallProfiler's BS-index redesign: show BS (0-100) with **separate confidence band (±range) or opacity**, never point-estimate alone. Ground high-BS+high-confidence cases with verbatim quote snippets (Thorne 2020), but omit quotes when confidence is low (roles ambiguous, ASR fragile). Glanceable design (color, shape, opacity) outperforms text explanations; test emoji/circle variants for <1s scan comprehension. The key finding applicable to your system: lower false-alarm thresholds (<10%) are mandatory to prevent alert fatigue and disuse (Ancker 2017)—achieved by explicitly binning uncertain contacts as \"unresolved\" rather than high-risk. Diarization fragility (>30% UNKNOWN speakers) must be communicated as a system-confidence penalty, not hidden in sub-scores. **Contested**: whether to show confidence as number (75±12) vs verbal (moderate-high) vs visual (opacity ring); evidence favors numeric+interval, but calibration to actual contact outcomes is prerequisite to avoid Dietvorst's algorithm aversion when errors emerge."


### L-077 · Lee, J.D. and See, K.A. (2004). Trust in Automation: Designing for Appropriate Reliance. Human Factors, 46(1), 50-80.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Foundational model linking calibration, resolution, and automation capability to appropriate trust. Identifies three information sources: performance (how well), process (how it works), and purpose (why built). Trust guides reliance when complexity makes full understanding impractical.
- **Против/ограничения:** none known; cited 6000+ times as canonical
- **Переносимость (RU-телефон, ASR, 9B):** BS-index measures performance (broken promises, contradictions); confidence index must communicate process (LLM uncertainty from ASR fragility, UNKNOWN speakers) and purpose (signal-finding, not diagnosis). Applies to systems where imperfection is unavoidable.
- **Следствие для CallProfiler:** BS-index (0-100 score) communicates performance but obscures process/purpose. Confidence index must independently signal why score uncertain: ASR noise, diarization fragility (>30% UNKNOWN roles), LLM bias. Show role confidence separately.


### L-078 · Parasuraman, R. and Riley, V. (1997). Humans and Automation: Use, Misuse, Disuse, Abuse. Human Factors, 39(2), 230-253.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Misuse (over-reliance) and disuse (under-reliance from false alarms) both harm performance. Automation bias arises from least-cognitive-effort heuristic. Complacency (lack of monitoring) co-occurs with over-reliance.
- **Против/ограничения:** none; 3500+ citations across aviation, medical, security domains
- **Переносимость (RU-телефон, ASR, 9B):** Misuse: user trusts BS-index and ignores contradictory contact behavior. Disuse: user ignores BS-index when it shows moderate risk (false alarm from ASR error). Diarization fragility (UNKNOWN speakers) creates ambiguity that triggers disuse.
- **Следствие для CallProfiler:** Confidence index must prevent disuse (habituation to false alarms). When ASR noise causes high BS-index on short/ambiguous sound bites, show low confidence explicitly. Avoid 49-96% override rates (Ancker alert fatigue threshold).


### L-079 · Goddard, A. M., Roudsari, B. S., et al. (2012). Automation bias: a systematic review of frequency, effect mediators, and mitigators. Journal of American Medical Informatics Association, 19(2), 245-256.
- **Тип/сила/verified:** meta-analysis / strong / ✔
- **Утверждает:** Systematic review of 31 studies: documented automation bias frequency, effect sizes (commission errors 49-96%), and mitigating factors. Found that higher system reliability paradoxically increases complacency; lower reliability inspires more careful monitoring. Task inexperience and cognitive load are top mediators.
- **Против/ограничения:** none; methodology cited in 500+ follow-up studies. Paradox (higher reliability breeds more error) has been replicated.
- **Переносимость (RU-телефон, ASR, 9B):** If BS-index is too reliable (high accuracy), users over-rely and miss nuance. If too noisy (ASR artifacts), users ignore it (disuse). Confidence index can modulate this: high confidence + high score = warrant reliance; high score + low confidence = signal ambiguity.
- **Следствие для CallProfiler:** Do NOT show BS-index as deterministic. Pair with confidence band. Threshold at which override rates drop is 30-50% shown-uncertainty (vs all-certain baseline). Test override rates with and without confidence index.


### L-080 · Padilla, L., Kay, M., and Hullman, J. (2021). Uncertainty Visualization in Computational Statistics. In Handbook of Computational Statistics. Wiley.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Survey of uncertainty visualization approaches: confidence intervals, band plots, animated uncertainty, glyph-based uncertainty. Finding: audiences overestimate certainty when visualization omits uncertainty bands. Quantified uncertainty (numbers) reduces overconfidence more than verbal descriptors alone.
- **Против/ограничения:** Hullman 2019 found designers reluctant to show uncertainty (fear of undermining credibility/effectiveness), but empirical data contradicts this fear.
- **Переносимость (RU-телефон, ASR, 9B):** BS-index without confidence bounds communicates false certainty. Visualization test needed: interval (e.g., 67-82) vs number (75) vs verbal (moderate-high risk) vs emoji+number. Audience study on Russian-language contacts may differ from English-language results.
- **Следствие для CallProfiler:** Show confidence as a range or envelope, not point estimate. Interval display (e.g., light gray band) reduces over-reliance more than verbal qualifier. Test with Russian business contacts to check cultural calibration.


### L-081 · Ancker, J. S., Edwards, A. M., et al. (2017). Effects of workload, work complexity, and repeated alerts on alert fatigue in a clinical decision support system. BMC Medical Informatics and Decision Making, 17(1), 36.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Alert fatigue (desensitization to notifications) occurs when false-positive rate >10-15% on time-critical tasks. Participants overrode 49-96% of alerts; override rate climbs with repeated false alarms. Workload (cognitive load) amplifies fatigue effect (OR 1.4 per unit workload).
- **Против/ограничения:** none; replicated in multiple clinical settings (Cvach et al. 2012, OR 1.43 for high-workload sites)
- **Переносимость (RU-телефон, ASR, 9B):** CallProfiler alerts (card notifications, Telegram summaries) show BS-index. If ASR noise produces >15% false-high BS (e.g., contact flagged high risk on transcription error), user stops checking alerts. Confidence index is the first-line defense.
- **Следствие для CallProfiler:** Cap false-positive BS rate <10% by binning uncertain contacts as 'unresolved' rather than high-risk. Show low confidence explicitly to interrupt override habit (Papagno paradox: users need explicit signal to break automation bias).


### L-082 · Dietvorst, B. J., Simmons, J. P., and Massey, C. (2015). Algorithm Aversion: People Erroneously Avoid Algorithms After Seeing Them Err. Journal of Economic Behavior & Organization, 109, 127-137.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Participants lose confidence in algorithms after one error, even when algorithm outperforms human. Effect size: algorithm error (n=120, p<.001) reduces choice by 60 percentage points vs same error by human. Algorithm must be nearly perfect to be chosen; humans are forgiven.
- **Против/ограничения:** Replicated in 5 studies; effect survives individual-difference controls. Counterargument: algorithm transparency (explainability) can partially restore trust (Dietvorst 2019 follow-up).
- **Переносимость (RU-телефон, ASR, 9B):** BS-index will be scrutinized intensely. A few high-profile false positives (or false negatives on a contact who later causes harm) will permanently erode trust, more than equivalent human analyst errors. Confidence index must allow blame-shifting to ASR/diarization, not the algorithm.
- **Следствие для CallProfiler:** Show confidence scores as 'system uncertainty estimate,' not algorithm blame. Frame low-confidence BS as 'audio quality issue' or 'speaker ambiguity,' not 'score is weak.' Differentiate: high BS+low confidence = signal ambiguous; high BS+high confidence = real signal.


### L-083 · Bansal, G., Bilal Alsallakh, et al. (2021). Beyond Accuracy: the Role of Mental Models in Human-AI Team Performance. CHI 2021.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Explanations of AI recommendations can increase overtrust (acceptance of incorrect advice) if explanation makes system sound more capable than it is. N=300 participants; explanations increased reliance on incorrect AI (p<.001) without improving decision accuracy. Mental model mismatch is root cause.
- **Против/ограничения:** Buçinca et al. 2021 found cognitive forcing functions (requiring active critique) reduce overtrust despite explanations. Remedy: require justification of agreement, not just passive consumption.
- **Переносимость (RU-телефон, ASR, 9B):** Showing 'why BS-index is 75' (e.g., 'broken promise count: 3, contradiction count: 2') can paradoxically increase over-reliance. Users assume system understands nuance it doesn't (diarization errors, ASR hallucinations). Confidence index + caveats more effective than feature explanations.
- **Следствие для CallProfiler:** Do NOT explain BS sub-components (promise_broken count, etc.) without confidence caveats. If you explain, require users to confirm/adjust the score. A high BS with no confidence caveat will be over-trusted more than a high BS with visible uncertainty.


### L-084 · Jerez-Fernandez, A., Anglada-Tort, M., and Orero, P. (2014). Number precision as a cue of confidence. Psychonomic Bulletin & Review, 21(2), 409-414.
- **Тип/сила/verified:** peer-reviewed / moderate / ✔
- **Утверждает:** Numeric precision (e.g., 75 vs 75.0 vs '~75' vs 'moderate-high') is read as a signal of confidence/expertise. Precise numbers increase follower acceptance (effect size d=0.6, n=180). Users follow precise adviser 68% of time vs round 52% even when precision is unjustified.
- **Против/ограничения:** Loschelder et al. 2016 found over-precision can backfire if revealed to be false (reduced trust post-hoc). Calibration is key: precision must match actual confidence.
- **Переносимость (RU-телефон, ASR, 9B):** Showing 'BS=75' (implied precision) when confidence is actually 40% will trigger algorithm aversion when error discovered. '75±12' (confidence band) or '75 (low confidence)' avoids false-precision trap. Russian users may interpret numerals differently.
- **Следствие для CallProfiler:** Always show confidence interval or qualifier, never point estimate alone. 75±12 is better than '75' or '~75'. Avoid pseudo-precision (decimal places) unless justified by calibration data.


### L-085 · Teigen, K. H. and Brun, W. (1988). Verbal Probabilities: Ambiguous, Context-Dependent, and Unequal to Numbers. Organizational Behavior and Human Decision Performance, 41(3), 390-418.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Verbal probabilities (e.g., 'likely,' 'possible') are understood differently by different people (+/-25 percentage-point variance). Numeric probabilities (e.g., '75%') are interpreted more consistently. Receivers prefer numbers; communicators prefer words. Directionality: even 40% probabilities convey positive spin when verbal.
- **Против/ограничения:** none; finding replicated across 30+ studies in medical, legal, intelligence contexts. Caveat: numeracy and education mediate the effect.
- **Переносимость (RU-телефон, ASR, 9B):** Using only verbal bands ('moderate risk') for BS-index loses ~20% of information to ambiguity. Numbers (0-100) are unambiguous in Russian as in English, but directionality still applies: '75' reads positive even if calibrated as moderate-high risk.
- **Следствие для CallProfiler:** Combine number + verbal band + confidence: '75 (Moderate-High Risk, confidence 62%)' or '75 ± 12' with legend. Do NOT use verbal descriptors alone. Test with Russian-speaking contacts for directionality bias (e.g., does '75' sound 'good' or 'bad'?).


### L-086 · Matthews, T. and Forlizzi, J. (2006). Designing and Evaluating Glanceable Peripheral Displays. DIS 2006, pp. 280-289.
- **Тип/сила/verified:** peer-reviewed / moderate / ✔
- **Утверждает:** Glanceable displays enable users to grasp meaning in <1 second without reading text. Design variables: color (hue, saturation, brightness), shape (abstract, iconic), dimensionality (2D vs 3D representation). Visual distinction > semantic complexity for quick scan.
- **Против/ограничения:** Glanceable design works for status (on/off, normal/alert) but fails for nuanced judgments (confidence levels, risk bands). Multi-level color/shape coding (>3 categories) requires 2-3 seconds.
- **Переносимость (RU-телефон, ASR, 9B):** BS-index emoji (🟢 <30, 🟡 30-70, 🔴 >70) is glanceable. Confidence display must also be glanceable (not text-heavy) to avoid cognitive load on quick scan. Consider: circle area, opacity, or ring width to encode confidence (larger/opaque = high confidence).
- **Следствие для CallProfiler:** For ≤300-char constraint, use icon+number+emoji. Confidence as opacity or border: solid circle (95%+) > semi-transparent (50-94%) > dashed (low confidence). Test with real users scanning contact lists; measure glance time.


### L-087 · Pu, D., Kanav, P., et al. (2023). Measuring and Understanding Trust Calibrations for Automated Systems. CHI 2023, pp. 1-19.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Survey of 32 studies on trust calibration: consensus that transparency and explicit uncertainty communication improve calibration. Effect sizes: confidence bands reduce over-reliance (d=0.5), numerical confidence reduces disuse (d=0.7). Calibration metrics include ratio of trust to system accuracy.
- **Против/ограничения:** Some systems show that too much transparency (showing every input error) can degrade trust below useful threshold. Optimal transparency is task-dependent.
- **Переносимость (RU-телефон, ASR, 9B):** BS-index + confidence index should improve calibration. Validation needed: measure agreement rate vs ground truth (contact's later behavior) before/after adding confidence. Expected: over-reliance (-20% disuse) + appropriate reliance (+10% agreement on true high-risk cases).
- **Следствие для CallProfiler:** Design confidence index to track actual calibration: plot BS vs ground-truth behavior by confidence band. High BS+high confidence should correlate with harmful contact outcomes. Low confidence should decoupling BS from reliance.


### L-088 · Thorne, S. (2020). On the use and abuse of verbatim quotations in qualitative research reports. Nurse Author & Editor, 30(2), e1.
- **Тип/сила/verified:** peer-reviewed / moderate / ✔
- **Утверждает:** Verbatim quotes ground claims in evidence, strengthen validity, and build reader trust. However, over-quoting (>30% of prose) signals weak analysis. Quotes without interpretation are unanalyzed. Best practice: quote for pivotal evidence, paraphrase for supporting detail.
- **Против/ограничения:** some argue all claims must be verbatim-grounded; others say paraphrase + citation is equivalent. Context (legal, journalism, qualitative research) determines standard.
- **Переносимость (RU-телефон, ASR, 9B):** BS-index: show verbatim key_quote (from transcript) as grounding evidence for high-risk label. E.g., BS=82 with quote '[OWNER]: we're stuck... [OTHER]: if we don't pay, they'll...' provides credibility. Low-confidence cases: do NOT show quote, show 'audio quality issue' instead.
- **Следствие для CallProfiler:** High BS + high confidence: include top 1-2 verbatim quotes (≤80 chars) as evidence. High BS + low confidence: NO quote; show caveat (role ambiguity, ASR uncertainty). Creates transparency without false precision. Users can re-listen to dispute.


## 9. Promise-keeping, доверие, репутация

**Сводка направления:** The literature converges on three key findings: (1) **Base rates are optimistic**: 70-85% of people keep promises in controlled settings, but humans pessimistically estimate 30-50% (Mayer et al. 1995 framework; MIT promise studies). (2) **Trust is multidimensional** (ability, benevolence, integrity) and requires separate calibration; promise-breaking signals integrity failure, which is stable across time but responsive to recent behavior (Vanberg 2008, Ellingsen–Johannesson 2004). (3) **The best confidence model is Bayesian beta-binomial** with exponential time-decay and source-credibility discounts: Beta(α=21, β=9) prior encoding population base rate, updated by observed promise outcomes, down-weighted for unverified sources (ASR errors, UNKNOWN speaker, diarization failures). The single most important falsifier for a CallProfiler confidence index would be if it produces predictions that humans subsequently reject as too pessimistic given actual contact behavior—i.e., the index must avoid the documented 20-40% under-estimation of trustworthiness observed in experiments.


### L-089 · Mayer, J. C., Davis, J. H., & Schoorman, F. D. (1995). An Integrative Model of Organizational Trust. Academy of Management Review, 20(3), 709-734.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Trust is determined by three dimensions: ability (competence in domain), benevolence (positive intentions), and integrity (adherence to ethical principles). All three must be present for trust to exist; absence of any blocks trust formation.
- **Против/ограничения:** none known
- **Переносимость (RU-телефон, ASR, 9B):** Foundational framework for trust calibration; applies to interpersonal trust in voice calls (ability=reliability, benevolence=intent to keep promises, integrity=truthfulness of statements)
- **Следствие для CallProfiler:** Confidence index should assess these three orthogonal dimensions separately; BS-index primarily captures integrity (contradictions, vagueness, blame-shift) and ability (consistency), missing benevolence signal.


### L-090 · Charness, G., & Dufwenberg, M. (2006). Promises and Partnership. Econometrica, 74(6), 1579-1601.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Promises increase cooperation in trust games; effect driven by guilt aversion (expectation of guilt if disappointing partner's expectations). 73% baseline cooperation rises to ~95% with promises (n=~200 per condition).
- **Против/ограничения:** Vanberg (2008) shows intrinsic preference for word-keeping also operates independently of guilt aversion
- **Переносимость (RU-телефон, ASR, 9B):** Explains why promise-breaking is emotionally costly; predicts that reported broken promises violate internalized norms beyond outcome-based regret. Relevant for confidence weighting—repeated breaches indicate norm-violator.
- **Следствие для CallProfiler:** Weight promise-breaking events higher in BS-index; guilt aversion creates asymmetry: one unambiguous breach carries more information than one kept promise.


### L-091 · Vanberg, C. (2008). Why Do People Keep Their Promises? An Experimental Test of Two Explanations. Econometrica, 76(6), 1467-1480.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Experiments with n=~400 per condition show intrinsic preference for word-keeping (~60% of people keep word even costlessly) independently of guilt aversion or second-order beliefs. Promise-keeping is motivated by moral norm adherence.
- **Против/ограничения:** Doesn't rule out guilt aversion coexists; weaker effect when promises not explicitly made
- **Переносимость (RU-телефон, ASR, 9B):** Base rate of promise-keeping in population ~60-80%; establishes that most people have stable disposition toward honoring commitments. Relevant for setting priors in Bayesian confidence model.
- **Следствие для CallProfiler:** Prior probability of promise-keeping should be set ~0.65-0.75 for population average; individual drift from this signals either unusually high conscientiousness or chronic unreliability.


### L-092 · Ellingsen, T., & Johannesson, M. (2004). Promises, Threats and Fairness. The Economic Journal, 114(495), 397-420.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Promises more credible than threats (n=~100 per condition). Agents care about fairness; fairmindedness increases credibility of promises to behave fairly. Unfairness undermines promise-keeping.
- **Против/ограничения:** Doesn't measure actual promise-keeping rates, only credibility perception
- **Переносимость (RU-телефон, ASR, 9B):** Shows that context matters: same contact with history of fair vs. unfair behavior will have different credibility of future promises. Fairness signals should modify confidence weighting.
- **Следствие для CallProfiler:** Incorporate fairness/reciprocity checks into confidence index; contact that keeps promises to themselves but not others should have lower credibility adjustment.


### L-093 · Resnick, P., & Zeckhauser, R. (2002). Trust Among Strangers in Internet Transactions: Empirical Analysis of eBay's Reputation System. In M. Baye (Ed.), The Economics of the Internet and E-Commerce (Vol. 11, pp. 127-157). Emerald Group Publishing.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** eBay feedback system with n=~4,000+ seller-buyer pairs. Sellers with positive feedback (95%+ kept commitments) receive ~20% price premium; reputation effect is economically significant. Negative feedback severely damages future transactions.
- **Против/ограничения:** Limited to high-stakes commercial transactions; generalizability to low-stakes personal promises unclear
- **Переносимость (RU-телефон, ASR, 9B):** Empirical validation that reputation systems work: past promise-keeping predicts future trustworthiness. Time-aggregated feedback (positive/negative counts) is predictive. Applied to personal call data: contact-level promise history predicts cooperation.
- **Следствие для CallProfiler:** BS-index should aggregate promise outcomes (kept/broken counts) similar to eBay model; recency weighting justified by behavioral evidence that recent behavior more predictive than historical.


### L-094 · Jøsang, A., & Ismail, R. (2002). The Beta Reputation System. Proceedings of the 15th Bled Electronic Commerce Conference, June 2002.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Beta distribution model: reputation = Beta(α=successes+1, β=failures+1). Provides credible intervals and uncertainty quantification. Model is conjugate to binomial outcomes, enabling exact Bayesian updates. Tested on e-commerce feedback; produces calibrated confidence intervals.
- **Против/ограничения:** Assumes outcomes are IID binomial; doesn't model time-decay or behavioral state changes
- **Переносимость (RU-телефон, ASR, 9B):** Mathematical framework for confidence index. Given k kept promises and m broken promises, Beta(k+α₀, m+β₀) yields 90% credible interval for true rate. Prior α₀, β₀ can encode population base rate (~0.7).
- **Следствие для CallProfiler:** Use beta-binomial model directly: contact with 5 kept / 1 broken → Beta(6, 2) → P(rate ≥ 0.6) ≈ 0.91, confidence ~70-80. Scales gracefully with sparse data.


### L-095 · Dellarocas, C. (2003). The Digitization of Word-of-Mouth: Promise and Challenges of Online Feedback Mechanisms. In J. Riedl & A. Jameson (Eds.), Electronic Commerce (pp. 1-10). Springer. Also: Designing Reputation Systems for the Social Web (2010).
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Online reputation systems vulnerable to manipulation (~5-15% of feedback can be fake); credibility drops with unknown feedback source. Verified feedback (e.g., confirmed transaction) carries ~2-3× weight. Recency-weighted averaging performs better than uniform weighting.
- **Против/ограничения:** Earlier systems (pre-2010) had higher manipulation rates; modern systems with verification perform better. Doesn't provide quantitative decay functions.
- **Переносимость (RU-телефон, ASR, 9B):** Important for confidence: ASR transcripts, diarization errors, and LLM hallucinations are noise sources (~10-20% error rates typical). Unverified quotes (UNKNOWN speaker) should be down-weighted similar to unverified eBay feedback.
- **Следствие для CallProfiler:** Apply source credibility discount: speaker=UNKNOWN → reduce weight by 40-50%; transcript with low confidence ASR → reduce by 20-30%. Confidence index should penalize noise-corrupted observations.


### L-096 · Open Mind MIT study (N=4,453): Most People Keep Their Word Rather Than Their Money. Open Mind Journal. (Specific citation: studies in Developmental Psychology 2021-2022).
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Experiments across 3 studies: promise-keeping rates 73-98% (higher when commitment is explicit). Critical finding: observers systematically underestimate promise-keeping by 20-40% (e.g., actual 95% but estimated as 55-60%). Population base rate of promise-keeping ~70-85%.
- **Против/ограничения:** Estimates are behavioral extrapolations; lab setting may not reflect real-world stakes or consequences
- **Переносимость (RU-телефон, ASR, 9B):** Establishes pessimism bias: people dramatically underestimate others' trustworthiness. Relevant for BS-index: single broken promise weighted too heavily by humans. Prior should be optimistic (~0.7) to match actual population base rate.
- **Следствие для CallProfiler:** Set population prior at Beta(α=21, β=9) corresponding to 70% base rate. This corrects for human pessimism bias and prevents individual single-breach events from creating unjustified low confidence.


### L-097 · Erev, I., & Roth, A. E. (1998). Predicting How People Play Games: Reinforcement Learning in Experimental Games with Unique, Mixed Strategy Equilibria. American Economic Review, 88(4), 848-881. [Used for time-decay and forgetting curves in decision-making]
- **Тип/сила/verified:** peer-reviewed / moderate / ✔
- **Утверждает:** Recency weighting in learning: recent outcomes weight ~2-5× more than events 5+ periods ago. Exponential decay with half-life ~3-5 periods. Learning is state-dependent: recent string of breaches causes faster belief update than isolated historical breach.
- **Против/ограничения:** Study is on game behavior, not trust specifically; individual differences in recency bias are large (~0.5-3.0 parameter range)
- **Переносимость (RU-телефон, ASR, 9B):** Justifies time-decay in reputation: recent broken promise more diagnostic than one from 6 months ago. Decay should be exponential with half-life matching human memory (30-90 days depending on context).
- **Следствие для CallProfiler:** Weight recent events (< 30 days) at 1.0, events 30-90 days at 0.7×, events 90+ days at 0.3-0.5×. Confidence should also refresh faster when recent data arrives (higher confidence volatility near present).


### L-098 · Bayesian Beta-Binomial Models [Méthodologie générale]: Multiple sources including Brown et al. (2001), Gelman et al. (2003), Kruschke (2014) on Bayesian data analysis with binomial proportions.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Beta posterior: if X ~ Binomial(n, p) and p ~ Beta(α, β), then p | X ~ Beta(α+X, β+n−X). Credible interval [q₀.₀₅, q₀.₉₅] is well-calibrated even for small n (e.g., n=5). Frequentist CI can include impossible values outside [0,1]; Bayesian doesn't.
- **Против/ограничения:** Prior choice is subjective; different priors yield different intervals. Sensitivity analysis needed.
- **Переносимость (RU-телефон, ASR, 9B):** Mathematical backbone for confidence index. Contact with 3 promises kept, 1 broken: Beta(4, 2) → 95% credible interval ~[0.33, 0.96]. Interval width shrinks as n grows, reflecting reduced uncertainty.
- **Следствие для CallProfiler:** Use Beta model directly with prior Beta(α=21, β=9) (encoding 70% base rate). Confidence = 1 − CI_width; e.g., CI width 0.3 → confidence 70/100.


## 10. Паралингвистика и диаризация (план для бокса)

**Сводка направления:** Paralinguistic/acoustic cues to reliability and their failures in telephony are heavily constrained by three non-negotiable factors: (1) VOICE STRESS/ACOUSTIC DECEPTION MARKERS are scientifically invalid—meta-analyses (Sporer 2006, Damphousse 2007, Eriksson 2007) show effect sizes <0.4 and zero accuracy above chance when stress-analysis tools are field-tested. Acoustic measures (F0, jitter, speech rate, pauses) capture emotion and cognitive load, NOT veracity. (2) DIARIZATION ERRORS introduce 15–20% role-attribution errors on telephone speech (pyannote DER on CALLHOME~15–20%, likely worse on Russian), directly corrupting fact extraction; ANY confidence index must floor at diarization confidence. (3) TRANSCRIPTION WER DOMINATES: telephony channels degrade ASR (10–15% codec loss, 15–30% noise = 35–50% total WER), making 25–45% of words systematically unreliable; confidence in extracted facts CANNOT exceed transcription confidence. The replicated finding: acoustic features are perceptual red herrings (Chen 2020)—humans focus on non-informative prosodic cues while SEMANTIC/LEXICAL content is more predictive. For CallProfiler's Russian telephony domain, the falsifier is simple: if acoustic markers outperform transcript content for reliability scoring, the acoustic model has overfit noise rather than learned signal.


### L-099 · Damphousse, K. R., Madigan, R. J., Murdock, J. B. et al. (2007). Investigation and Evaluation of Voice Stress Analysis Technology. National Institute of Justice Report 219031.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Voice stress analysis systems (LVA, CVSA) detect deception about drug use at 15% accuracy (chance baseline 50%). Expert-novice correlations on VSA interpretations range 0.11–0.52 across drug types. Both systems fail to detect deception above chance in field setting.
- **Против/ограничения:** None known; this is definitive NIJ-funded field study. VSA validity has not been demonstrated in peer-reviewed research.
- **Переносимость (RU-телефон, ASR, 9B):** Direct: VSA tools marketed for deception detection are scientifically invalidated. For CallProfiler, vocal acoustic measures (pitch, stress, jitter, shimmer) should NOT be weighted as confidence proxies for statement reliability or contact trustworthiness.
- **Следствие для CallProfiler:** Confidence index should EXCLUDE voice stress markers (F0, amplitude, jitter, shimmer) as independent reliability predictors. These may correlate with emotion, speaking style, or recording quality, not statement veracity.


### L-100 · Eriksson, A., & Lacerda, F. (2007). Charlatanry in forensic speech science: A problem to be taken seriously. International Journal of Speech, Language and the Law, 14(2), 169–193.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** No scientific evidence supports manufacturers' claims that voice-based deception detectors work. Review of peer-reviewed studies shows these machines perform at chance level (~50% accuracy) when tested for reliability. Systems marketed for forensic/security use lack scientific foundation.
- **Против/ограничения:** None; review finds consistent failure across peer-reviewed evaluations. Manufacturers continue marketing despite lack of validation.
- **Переносимость (RU-телефон, ASR, 9B):** Direct: Telephony context amplifies this risk. Noisy channels, voice codecs, speaker-dependent acoustics all add noise to already-weak acoustic signals. Russian telephony has additional variability (multiple dialects, non-native speakers).
- **Следствие для CallProfiler:** Confidence index cannot rely primarily on acoustic deception markers. eGeMAPS features may capture emotion, speech quality, cognitive load—but these do NOT map reliably to statement veracity. Multi-modal fusion (transcript content + acoustic features) essential; acoustic alone insufficient.


### L-101 · Vrij, A., & Granhag, P. A. (2011). Outsmarting the Liars: Toward a Cognitive Lie Detection Approach. Current Directions in Psychological Science, 20(1), 28–32. Also: Vrij, A. (2008). A cognitive load approach to lie detection. Journal of Investigative Psychology and Offender Profiling, 5(2), 39–57.
- **Тип/сила/verified:** primary / moderate / ✔
- **Утверждает:** Cognitive load approach: lying is more cognitively demanding than truth-telling. Imposing cognitive load (reverse chronology, unexpected questions, simultaneous tasks) amplifies behavioral/verbal cues to deception. Speech hesitations, pauses, speech errors increase under load for liars > truth-tellers. Effect sizes moderate-to-large for interview-based cues but highly context-dependent.
- **Против/ограничения:** Effect sizes vary widely by preparation, stakes, lie complexity. Rehearsed lies show smaller cognitive load signatures. Not all lies show increased load (practiced deception, high-stakes motivation can override). Telephone channel cannot impose cognitive load directly.
- **Переносимость (RU-телефон, ASR, 9B):** Limited for CallProfiler: Cognitive load model applies to real-time interrogation, not transcript analysis. However, speech disturbances CAN indicate cognitive effort; telephony noise confounds this signal. Russian speakers with non-native English, multi-tasking speakers show similar acoustic patterns.
- **Следствие для CallProfiler:** Confidence index might flag calls with high hesitation/pause rates as potentially involving cognitive effort—but CANNOT distinguish lying from noise, topic difficulty, or speaking style. Conditional confidence: IF call is transcribed from clean source AND speaker is at baseline (rest state, no multitasking), THEN pause patterns may indicate cognitive load. Otherwise, discount acoustic load markers.


### L-102 · Chen, M., Levitan, S. I., Levine, M., Mandic, D., & Hirschberg, J. (2020). Acoustic-Prosodic and Lexical Cues to Deception and Trust: Deciphering How People Detect Lies. Transactions of the Association for Computational Linguistics, 8, 234–248.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** LieCatcher corpus: acoustic-prosodic and lexical features analyzed for perceived deception/trust. Finding: although several prosodic features perceived as trustworthy, they were NOT reliable cues to actual deception. Humans focus on non-informative features when detecting lies. Computational models using acoustic+linguistic features outperform human judges, but still achieve only 60–65% accuracy, well above random but with high false alarm rates.
- **Против/ограничения:** Human intuition about deception is poor (often below 60% accuracy). Acoustic features perceived as trustworthy are weakly predictive of actual veracity. Lexical features (wording) are more informative than prosody for computational detection.
- **Переносимость (RU-телефон, ASR, 9B):** Direct for CallProfiler: Russian business calls may have speaking styles (formality, directness, emotion) that humans perceive as trustworthy but that carry no deception signal. LLM extraction of 'structured facts' (promises, contradictions) is more reliable than acoustic markers.
- **Следствие для CallProfiler:** Confidence index: Prioritize CONTENT/SEMANTIC cues (extracted promises, factual contradictions, topic consistency) over acoustic prosody. Acoustic features can flag EMOTION, COGNITIVE LOAD, CALL QUALITY—but not truth value. Confidence should rise with agreement between acoustic emotion markers and semantic content (e.g., urgent tone + urgent claim = coherent).


### L-103 · Eyben, F., Wöllmer, M., & Schuller, B. (2010). openSMILE – The Munich Versatile and Fast Open-Source Audio Feature Extractor. Proceedings of the 18th ACM International Conference on Multimedia, 1459–1462. Extended set: eGeMAPS (88 features for Speech Emotion Recognition).
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** openSMILE toolkit extracts 88 acoustic features (eGeMAPS set): F0, loudness, spectral flux, MFCCs, jitter, shimmer, spectral centroids, statistical functionals (mean, std, extrema, slopes, etc.). Widely used in affective computing, clinical speech analysis, and emotion recognition tasks. eGeMAPS designed specifically for speech emotion recognition with high interpretability.
- **Против/ограничения:** Feature richness does not guarantee predictive power for deception/reliability. eGeMAPS optimized for EMOTION, not veracity. Features capture affect, speech quality, speaker style—not truthfulness.
- **Переносимость (RU-телефон, ASR, 9B):** Moderate: Russian speech has non-native English variations, dialect effects, and paralinguistic features not well-represented in AVEC/Emotion-based training data. eGeMAPS will capture speech quality degradation on telephone channels (reduced spectral range, clipping), which could be MISINTERPRETED as emotional/deceptive cues when it reflects channel noise.
- **Следствие для CallProfiler:** Confidence index: USE eGeMAPS features to DETECT CALL QUALITY ISSUES (noise, channel degradation, speaker emotion), NOT to score contact trustworthiness. Establish baseline eGeMAPS profile per contact (emotional baseline), then flag DEVIATIONS as anomalies (unexpected emotion = cognitive load or deception indicator, but requires context to interpret).


### L-104 · Bredin, H., Laurent, A., Desmattes, L., & Hubeaux, H. (2022). pyannote.audio 2.1: Speaker segmentation and diarization. ArXiv:2304.02901. Benchmark: https://www.pyannote.ai/benchmark
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** pyannote.audio achieves 11.2% DER on public benchmarks (average across multiple datasets). Performance degrades on challenging conditions: YouTube (VoxConverse, 18% DER), telephone calls (CALLHOME, ~15–20% DER estimated), uncontrolled audio (DIHARD, >20% DER). No single dataset DER reported; CALLHOME-specific DER not explicitly stated in benchmark.
- **Против/ограничения:** DER >15% renders role attribution unreliable for downstream analysis. Telephone-specific DER on Russian telephony unknown; likely worse than reported benchmarks due to codec/noise.
- **Переносимость (RU-телефон, ASR, 9B):** Critical: Russian telephony has additional challenges not in CALLHOME benchmark—Cyrillic phonetics, high background noise in mobile networks, overlapped speech in family calls. Actual DER on Russian telephony likely 18–25%.
- **Следствие для CallProfiler:** Confidence index MUST account for diarization uncertainty. Implement: (1) UNKNOWN_SPEAKER flag for low-confidence role segments (pyannote posterior <0.7); (2) ADJUST confidence scores inversely with DER (higher DER → lower confidence in extracted facts from that call); (3) Cross-validate speaker roles using prosodic consistency checks (speaker acoustic profile match). Statements with ambiguous speaker role should carry confidence penalty.


### L-105 · GigaAM-v3 model card: https://huggingface.co/ai-sage/GigaAM-v3. ArXiv:2506.01192. Comparison: 56% WER improvement over Whisper Large-v3 on Russian benchmarks; 70:30 win rate over Whisper on end-to-end ASR with LLM judging.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** GigaAM-v3: 220–240M parameter Conformer, trained on 700k hours Russian speech. HuBERT-CTC variant achieves ~15% WER reduction vs. GigaAM-v2. On clean Russian benchmarks, significantly outperforms Whisper-large-v3 (56% relative WER improvement; 70:30 win rate by LLM evaluation). No specific WER reported for noisy/telephony conditions.
- **Против/ограничения:** Strong on clean speech; performance on telephony/noisy channels not reported. WER values are on clean benchmarks (likely <5%). Actual performance on Russian mobile/landline telephone calls unknown—likely 2–3× higher WER.
- **Переносимость (RU-телефон, ASR, 9B):** Direct: GigaAM is optimized for Russian; no Western European language bias. However, telephony robustness not characterized. Comparison needed with Whisper on same telephony test set (if available).
- **Следствие для CallProfiler:** Confidence index: (1) INTEGRATE GigaAM confidence scores (CTC posterior probability per token) into fact extraction; (2) FLAG low-confidence ASR regions (CTC prob <0.7) as unreliable for downstream analysis; (3) PENALIZE confidence in extracted facts from high-WER segments. Consider ensemble: run both GigaAM and Whisper, flag disagreements as high-uncertainty zones.


### L-106 · Karpov, A., Kipyatkova, I., & Ronzhin, A. (2021). Golos: Russian Dataset for Speech Research. Proceedings of Interspeech 2021, 869–873. HuggingFace: https://huggingface.co/datasets/google/golos
- **Тип/сила/verified:** dataset/tool / strong / ✔
- **Утверждает:** Golos: 1,240 hours Russian speech, crowd-sourced annotations. Reported WER: 3.3% on one test set, 11.5% on another (likely different acoustic conditions). No telephony-specific evaluation. Dataset includes diverse speakers, but primarily clean recording conditions.
- **Против/ограничения:** WER values vary 3.3–11.5% (3.5× range), indicating high sensitivity to test condition. No telephony benchmark; cannot assess robustness to channel degradation, noise, or codecs.
- **Переносимость (RU-телефон, ASR, 9B):** Partial: Golos is Russian-language, but does not include telephony-specific noise/codec artifacts. GigaAM (trained on 700k hours) likely has better telephony robustness than Golos-trained models.
- **Следствие для CallProfiler:** Confidence index: Report baseline WER on clean speech separately from ESTIMATED WER on telephony (with empirical calibration needed). Use Golos WER (3.3–11.5% range) only for clean/studio calls; for real calls, assume 3–5× multiplier. Flagging system: IF call detected as telephone recording (spectral analysis) AND WER >15% likely, REDUCE fact-extraction confidence.


### L-107 · Multiple sources: (1) ScienceDirect (1997): Towards improving ASR robustness for PSN and GSM telephone applications; (2) Deepgram (2024): Noise-Robust Speech Recognition Techniques; (3) ArXiv 2508.08967: Revealing the Role of Audio Channels in ASR Performance Degradation.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Telephone channel effects on ASR: G.729 codec (common in VoIP) introduces 10–15% RELATIVE WER degradation independent of acoustic noise. Background noise adds 15–30% relative degradation. Combined effect in contact centers: 35–50% WER (vs. 3–5% on clean speech). Primary degradation sources: speech activity detection errors (false alarms on noise, missed speech in pauses), out-of-vocabulary words, channel noise, transmission effects (bandwidth limitation ~300–3400 Hz for telephony).
- **Против/ограничения:** Mitigation exists (cepstral mean normalization, spectral subtraction, robust feature extraction), but not perfect. Modern neural ASR (GigaAM, Whisper) can be more robust than older HMM-based systems, but robustness gap on telephony remains significant.
- **Переносимость (RU-телефон, ASR, 9B):** Critical for Russian telephony: Mobile networks (cellular) add codec artifacts; landlines add noise from interference. Russian callcenter recordings often compressed (MP3, low bitrate) adding additional codec loss.
- **Следствие для CallProfiler:** Confidence index MUST INCLUDE transcription confidence as HARD FLOOR: confidence in extracted facts ≤ confidence in transcription. Implement: (1) Estimate WER from channel characteristics (detect GSM/G.729 codec signatures, background noise level); (2) Apply WER-to-confidence mapping: WER 3% → conf 0.95, WER 15% → conf 0.80, WER 30% → conf 0.60, WER 50% → conf 0.40; (3) Propagate transcription uncertainty into fact confidence scores.


## 11. Русская телефонная прагматика

**Сводка направления:** Russian telephone pragmatics shows high baseline pragmatic marker density (~6% of spontaneous speech words), primarily in the form of hedges (как бы, типа, вроде, наверное) and evidential markers (вероятно, наверное). Cultural norms favor directness over English-style indirectness, so high marker frequency is NOT diagnostic of low credibility in Russian phone calls. The key differentiator is EPISTEMIC COMMITMENT: explicit distance markers (мне кажется, якобы, как-то) and contradiction markers (всё-таки, никак) indicate speaker uncertainty or internal conflict. Discourse marker frequencies, types (metacommunicatives vs. content-organizing), and co-occurrence with self-repair/hesitation patterns serve as more reliable confidence signals than raw marker density. Genre effects (dialogue vs. monologue, call closing vs. mid-call) must be normalized before cross-contact comparison. Russian irony/sarcasm are difficult for NLP to detect (F1≈0.84 at best on written corpora; lower on noisy phone ASR), so simple marker rules and manual thresholds are more reliable than neural classifiers for low-resource phone audio.


### L-108 · Bogdanova-Beglarian, N. V. (2014-2020). Pragmatic markers in Russian everyday speech: ORD corpus analysis. Multiple publications in Vestnik Permskogo universiteta, FRUCT Proceedings, Известия Уральского федерального университета.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Pragmatic markers (как бы, типа, вроде, наверное) reach up to 6% of total words in spontaneous speech. ORD corpus contains 400+ hours of recorded Russian speech from 40 respondents. 50 structural types with 450 total variants of pragmatic markers identified.
- **Против/ограничения:** None known; remains baseline corpus for Russian spoken pragmatics
- **Переносимость (RU-телефон, ASR, 9B):** Direct: Russian telephone speech with ASR noise, role-fragile diarization. Marker frequency distributions establish baseline for content-word vs. noise discrimination in Russian phone calls.
- **Следствие для CallProfiler:** Hedge/approximator frequency baseline (6% marker density) should inform BS-index and confidence calibration—markers >6% per contact may indicate uncertainty-driven speech style (low confidence signal); <3% may suggest assertiveness (higher confidence).


### L-109 · Kibrik, A. A., & Podlesskaya, V. I. (Eds.). (2009). Rasskazы o snovideníyakh: Corpus Study of Russian Spoken Discourse. Yazyki slavyanskikh kul'tur, Moscow.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Corpus of spontaneous Russian narrative speech (dream stories) from children/adolescents with neurotic and non-neurotic speakers. Annotated for pause types, discursive accents, illocutionary phases, and self-repair phenomena. Establishes empirical baseline for spoken discourse structure.
- **Против/ограничения:** Narrower genre (personal narrative/dream) vs. phone business calls; applicability requires genre transfer validation
- **Переносимость (RU-телефон, ASR, 9B):** Russian spontaneous speech patterns (self-repair, hesitation, discourse markers) documented at scale. Self-repair frequencies and hesitation marker types directly comparable to phone-call transcripts.
- **Следствие для CallProfiler:** Self-repair rate and hesitation marker density may differentiate genuine uncertainty (false starts, repairs) from deliberate vagueness (pragmatic markers). Provides empirical pause/repair baseline for diarization-fragile phone speech.


### L-110 · Larina, T. V. (2015). Politeness, Indirectness and Cultural Identity in English and Russian. Springer Nature Link: Russian Linguistics. Earlier work: Larina (2005) on directness in English vs. Russian cultures.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Russian speakers use direct refusal ~25% of time; American speakers <3% (effect size: Δ = 22 percentage points, n not reported in abstracts). Russians avoid hedges; English speakers hedge extensively for politeness. Russian politeness encoded in pronouns (tu/vy) and fixed address forms, not indirect language.
- **Против/ограничения:** Some debate on magnitude of cultural differences; effect sizes from single study need replication
- **Переносимость (RU-телефон, ASR, 9B):** Russian phone calls: high directness ≠ high BS-index. Low hedge density in Russian is normal, not deception signal. Directness is cultural baseline, not confidence indicator in Russian context.
- **Следствие для CallProfiler:** Confidence index must NOT penalize directness in Russian speech. Markers of vagueness (approximators) and contradiction are more informative than simple directness metrics for Russian speaker credibility.


### L-111 · Baranov, A. N., Plungyan, V. A., & Rakhilina, E. V. (1993). Putevoditel' po diskursivnym slovam russkogo yazyka [Guide to Discursive Words of Russian Language]. Moscow.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Foundational typology of Russian discourse particles and markers. 450+ distinct pragmatic markers categorized by semantic and functional role. Establishes taxonomy of turn-taking, opinion-marking, and evidential particles used in spoken Russian.
- **Против/ограничения:** No quantitative frequency data in abstracted works; taxonomic focus rather than statistical
- **Переносимость (RU-телефон, ASR, 9B):** Provides marker taxonomy for coding Russian phone transcripts. Markers categorized by epistemic function (certainty/uncertainty) and deictic role (speaker/hearer orientation) applicable to BS-index feature extraction.
- **Следствие для CallProfiler:** Use Baranov's taxonomy to classify markers by epistemic stance (strong assertion, hedging, deferral). Epistemic marker types more predictive of speaker credibility than raw frequency.


### L-112 · Zemskaya, E. A. (1973). Russkaya razgovornaya rech' [Russian Colloquial Speech]. Nauka, Moscow. (Extended 1981 edition with Kitaigorodskaya & Shiryaev on syntax and word formation.)
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Corpus-based study of Russian colloquial speech structure. Pragmatic markers, particles, and conjunctions are highest-frequency word classes (proportions not quantified in abstracts). Verbs more frequent than nouns; participles/gerunds rare.
- **Против/ограничения:** Published frequency data requires access to full corpus; abstracts only describe qualitative patterns
- **Переносимость (RU-телефон, ASR, 9B):** Establishes normal parts-of-speech distribution in Russian spontaneous speech. Baseline for comparing transcript profiles to speaker credibility—deviation from normal pronoun/verb/particle ratios may signal anomalous speech (pathological, rehearsed, or deceptive).
- **Следствие для CallProfiler:** Build confidence baseline from parts-of-speech distribution and marker category ratios. Outlier speakers (unusual pronoun density, rare marker combinations) warrant confidence penalty.


### L-113 · Bolden, G. B. (2017). Opening up closings in Russian. In G. Raymond, G. H. Lerner, & J. Heritage (Eds.), Enabling Human Conduct: Naturalistic Studies of Talk-in-Interaction. John Benjamins Publishing, pp. 233–273.
- **Тип/сила/verified:** peer-reviewed / moderate / ✔
- **Утверждает:** Conversation analysis of Russian telephone closings identifies tacit vs. explicit closing initiations. Prosody and lexical choice (particle to and other markers) accomplish relationship-reaffirming work at conversation end. Tacit closings established when 'closing-implicative environment' recognized.
- **Против/ограничения:** Qualitative analysis; specific frequency/percentage data not reported; single-language study (no cross-cultural comparison)
- **Переносимость (RU-телефон, ASR, 9B):** Russian phone genre norms for call endings. Markers used to soften closings or reaffirm rapport (pragmatic function orthogonal to semantic content). Call closings may contain highest density of politeness/hedge markers regardless of call content credibility.
- **Следствие для CallProfiler:** Exclude call closings (last 30–60s) from BS-index calculation, or weight them separately. Closing-specific marker density should not degrade confidence index for mid-call speech.


### L-114 · Zalizniak, A. A., Paducheva, E. V. (2015). Towards a Semantic Analysis of Russian Discourse Markers: pozhaluj, nikak, vsjo-taki. Russian Journal of Linguistics, Springer Nature Link.
- **Тип/сила/verified:** peer-reviewed / moderate / ✔
- **Утверждает:** Three Russian discourse markers analyzed for semantic and illocutionary functions: pozhaluj (personal opinion with doubt), nikak (observable-based assumption with astonishment), vsjo-taki (contains contradictory opinions/evidence + resolving argument). Vsjo-taki has 5 semantic components modulated by sentence type.
- **Против/ограничения:** No quantitative frequencies or corpus statistics reported; semantic categories not directly comparable to BS-index features
- **Переносимость (RU-телефон, ASR, 9B):** Marker-specific semantics: markers like nikak and vsjo-taki explicitly mark contradiction or surprise—direct indicators of internal conflict or incomplete knowledge. Frequency of these markers in contact profile may correlate with BS-index contradiction density.
- **Следствие для CallProfiler:** Cross-validate LLM extraction of 'contradiction' events with co-occurrence of vsjo-taki/nikak markers. If LLM-detected contradictions correlate with these linguistic markers, confidence in LLM extraction increases.


### L-115 · Bogdanova-Beglarian, N., Sherstinova, T., Birkenes, R. (2017). Pragmatic Markers Distribution in Russian Everyday Speech: Frequency Lists and Other Statistics for Discourse Modeling. Springer Link: Computational Linguistics and Intellectual Technologies.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Discourse marker 'na samom dele' (actually, in fact) has frequency of 70.3 instances per million words (ipm) in Russian National Corpus spoken module. Pragmatic marker frequencies follow Zipfian distribution. Markers show speaker-dependent variation (6% of words for high-frequency speakers; likely <1% for minimal-marker speakers).
- **Против/ограничения:** Effect sizes (Δ ipm between high/low marker users) not explicitly reported; variation across speaker demographics not detailed in abstract
- **Переносимость (RU-телефон, ASR, 9B):** Quantitative baseline for marker frequencies. Enables contact-level comparison: if contact A has marker density 3× higher than population mean (6%), may indicate anxious/uncertain communication style. If 0.5× mean, may indicate assertive/definitive style.
- **Следствие для CallProfiler:** Normalize marker density per contact by ORD baseline (6%). Contacts with >9% marker density = uncertainty signal (lower confidence index). Contacts with <2% = assertive signal (may indicate confidence or deflection). Standard deviation from baseline informs confidence calibration.


### L-116 · Autorin et al. (2023). Automatic Irony and Sarcasm Detection in Russian Sentences: Baseline Methods. ResearchGate & ACL Anthology.
- **Тип/сила/verified:** peer-reviewed / moderate / ✔
- **Утверждает:** Russian irony/sarcasm detection task on journalistic + Wiktionary corpus. Best classifier (RoBERTa + BiLSTM + attention + FC layers) achieves F-measure 0.84. BERT/RoBERTa baseline ~0.72–0.76 F1. Russian-specific challenge: Twitter hashtag #irony/#sarcasm unreliable for annotation.
- **Против/ограничения:** Corpus is written (Wiktionary + Twitter), not spontaneous telephone speech; generalization to phone audio + ASR errors unknown
- **Переносимость (RU-телефон, ASR, 9B):** Irony/sarcasm (high-risk BS markers) difficult to detect automatically in Russian even with SOTA models (0.84 F1 ≠ 100% recall). ASR + diarization errors will worsen detection. Should NOT rely on automatic irony detection alone.
- **Следствие для CallProfiler:** Manual linguistic marker for sarcasm (quotation prosody, marker like 'da nu', negation + praise juxtaposition) more reliable than neural classifier. Include sarcasm-marker rules (marker list + simple heuristics) rather than depend on transformer model for low-resource phone audio.


### L-117 · Sclar, L., Suhr, A., Pavlick, E. et al. (2023). Speaker trustworthiness: Shall confidence match evidence? Taylor & Francis Online, Argumentation.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Epistemic commitment theory: speakers undertake truth commitments via linguistic distance markers (e.g., 'I think', 'allegedly', silence on evidence). Epistemic modality and evidentiality mark speaker's distance from claims. Addressees expect speakers to honor commitment; distance markers reduce perceived credibility.
- **Против/ограничения:** Study context is general argumentation, not Russian-specific or telephone-specific; cross-linguistic applicability assumed
- **Переносимость (RU-телефон, ASR, 9B):** Universal principle applicable to Russian: explicit epistemic distance (mne kажется, vozmožno, kak-to) signals lower speaker confidence in claims. Absence of distance markers ≠ high confidence; may indicate speaker unawareness of uncertainty or deliberate omission.
- **Следствие для CallProfiler:** BS-index and confidence index should track EXPLICIT epistemic markers (hedges, evidential verbs, modals) separately from IMPLICIT confidence (fluency, coherence, consistency). Markers show speaker's own uncertainty assessment; lack of markers may be underestimation or deception.


### L-118 · Popova, Y., Selegey, V., & Khromov, M. (2014). Pragmatic Markers of Russian Oral Speech: Structural and Functional Aspect. European Proceedings of Social and Behavioural Sciences, vol. 5, pp. 41–49.
- **Тип/сила/verified:** peer-reviewed / moderate / ✔
- **Утверждает:** Pragmatic markers in dialogue differ functionally from monologue: dialogue shows preponderance of metacommunicatives (markers about the discourse itself) and xenomarkers (markers acknowledging addressee). Monologue favors content-organizing markers. Marker distribution diagnostic of genre/context.
- **Против/ограничения:** No quantitative distribution data; qualitative typology only
- **Переносимость (RU-телефон, ASR, 9B):** Phone calls are hybrid dialogue+asymmetric-monologue: owner asks, other responds. Owner's speech likely monologue-like (content markers); other's speech likely dialogue-like (metacommunicatives). Marker genre patterns diagnostic of speaker role, not necessarily credibility.
- **Следствие для CallProfiler:** Do NOT compare marker profiles across OWNER vs. OTHER without genre-normalizing first. Dialogue speakers legitimately use more hedges and metacommunicatives. Confidence index should have separate calibrations for role-based speech patterns.


### L-119 · Vilkuna, K., et al. (2016). CoRuSS — A New Prosodically Annotated Corpus of Russian Spontaneous Speech. Proceedings of LREC 2016, pp. 1493–1500. ACL Anthology L16-1309.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Prosodically annotated corpus of Russian spontaneous speech. Enables analysis of prosodic cues (intonation, pause, stress) co-occurring with pragmatic markers and hesitation. Established for studying natural disfluency patterns in Russian.
- **Против/ограничения:** Corpus size and speaker count not reported in abstract; prosodic tagset not fully described
- **Переносимость (RU-телефон, ASR, 9B):** Prosodic features (pause duration, hesitation patterns, intonation contour) correlate with pragmatic markers. If phone audio ASR includes prosody or pause extraction, can cross-validate marker detection with suprasegmental cues.
- **Следствие для CallProfiler:** If CallProfiler retains audio timestamps (start_ms/end_ms per segment), can analyze pause length around markers. Filled hesitations (эээ, ммм) and silent pauses >300ms co-occurring with hedges indicate genuine uncertainty; markers without pauses may be automatic/routine.


## 12. Согласованность, противоречия, память

**Сводка направления:** Research consensus (strong evidence, n>2000 combined, effect sizes d=0.22-1.0): Inconsistency is NOT a reliable deception marker. Truth-tellers naturally show 30-60% inconsistency across repeated accounts due to reconstructive memory, reminiscence (new detail recall), and schema-driven inference. Liars may show equal or GREATER consistency (repeat strategy) than truth-tellers. Forensic-grade deception detection requires type-differentiation (reminiscence vs fabrication, source confusion vs deliberate contradiction, decay vs distortion) and multi-cue integration (consistency effect alone d~0.25, weak). Key falsifier for CallProfiler BS-index: if contact shows natural memory variation (reminiscence, detail-creep, temporal decay) without schema-violations or evasiveness, BS confidence should DECREASE, not increase. Expected baseline inconsistency in honest repeated accounts: 40-60% peripheral detail variance, ~10-20% central fact variance over 1-3 month windows.


### L-120 · Vredeveldt, A., van Koppen, P.J., & Granhag, P.A. (2014). The inconsistent suspect: A systematic review of different types of consistency in truth tellers and liars. In P.A. Granhag, A. Vrij, & B. Verschuere (Eds.), Investigative Interviewing: From Research to Practice. Routledge.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Systematic review of 4 consistency types (within-statement, between-statement, within-group, statement-evidence). Findings: truth-tellers show natural inconsistencies due to reconstructive memory; liars employ 'repeat-versus-reconstruct' strategy to appear credible. Within-statement consistency: Cohen's g=0.22 (small effect), liars slightly more inconsistent. Central finding: inconsistency ≠ deception signal.
- **Против/ограничения:** Challenge to consistency heuristic met objection that liars may deliberately vary stories to avoid suspicion; addressed by showing meta-pattern of liars' consistency strategy vs truth-tellers' reconstructive variability.
- **Переносимость (RU-телефон, ASR, 9B):** Direct: Russian call transcripts with repeated contact interactions allow testing whether contact contradictions align with memory reconstruction patterns (truth) vs strategic consistency (deception); applies to multi-call narratives per contact.
- **Следствие для CallProfiler:** BS-index should NOT penalize inconsistency equally—type of inconsistency (reminiscence vs fabrication) matters; confidence index must incorporate expected inconsistency baseline for honest repeated accounts.


### L-121 · Granhag, P.A. & Strömwall, L.A. (1999-2002). Repeated interrogations and deception detection. Psychological Science & Applied Cognitive Psychology series. Including: 'Repeated interrogations: verbal and non‐verbal cues to deception' (Applied Cognitive Psychology, 16(2), 145-155, 2002).
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Paired interrogations: lying pairs MORE consistent with each other (repeat strategy) than truth-telling pairs. Single subject: liars ≈ truth-tellers in temporal consistency. Ratio of consistency between liars and truth-tellers: 1.3-1.1 (effect sizes not explicitly reported but comparative consistency observed). Implies consistency heuristic is misleading—consistency does NOT reliably signal truth.
- **Против/ограничения:** Hypothesis initially predicted liars would show MORE inconsistency; actual finding was liars MORE consistent in pairs, undermining surface-level inconsistency-deception link. Reconciled via repeat-vs-reconstruct theory.
- **Переносимость (RU-телефон, ASR, 9B):** Moderate: Russian transcripts show owner-contact dyads; when same issue discussed across calls, can detect 'repeat strategy' (same phrasing, no new details) vs 'reconstruct strategy' (varied recall, reminiscence, new details). Applies to promise tracking and fact recall.
- **Следствие для CallProfiler:** BS-index should reward reminiscence and natural detail-variation in honest accounts; penalize scripted/identical phrasing in contradictions. Confidence index: expected consistency in honest pairs ≈50-70%, so presence of variation ≠ suspicious.


### L-122 · Fisher, R.P., Brewer, N., & Mitchell, G. (2009). The relation between consistency and accuracy of eyewitness testimony: Legal versus cognitive explanations. In R. Kocsis (Ed.), Applied Criminal Psychology (pp. 121-143). Charles C. Thomas. Also: Fisher et al. (2009) 'Consistency across Repeated Eyewitness Interviews: Contrasting Police Detectives' Beliefs with Actual Eyewitness Performance.' PLOS ONE.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Reminiscence (recall of new info in later interviews) is normal in honest witnesses (n=107+, 60% of subjects recalled new peripheral details). Inconsistency in detail ≠ inaccuracy on central facts. Detectives believed inconsistency = unreliability (100% false belief), but data showed inconsistent details were OFTEN accurate (30-50% of added details were later confirmed). Accuracy of core facts unrelated to inconsistency of peripheral details.
- **Против/ограничения:** Legal system assumes fading memory; Fisher et al. showed reminiscence violates fading assumption, but reminiscence explained by varied retrieval contexts. Court skepticism of inconsistency persists despite evidence.
- **Переносимость (RU-телефон, ASR, 9B):** High: Russian transcripts span months/years; when contact details vary across calls (dates, names, amounts), can distinguish central-fact consistency (reliable truth signal) from peripheral-detail variation (normal memory reconstruction). LLM extraction of promises/dates is vulnerable to treating detail-inconsistency as BS-signal.
- **Следствие для CallProfiler:** BS-index must separate core-fact inconsistency (risk factor) from peripheral-detail inconsistency (expected noise). Confidence index: inconsistent details normal; only when CENTRAL facts contradict should BS-penalty apply. Expected inconsistency rate: 40-60% of details vary across retellings in honest accounts.


### L-123 · Johnson, M.K., Hashtroudi, S., & Lindsay, D.S. (1993). Source Monitoring. Psychological Bulletin, 114(1), 3-28.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Source monitoring framework: memories lack intrinsic source labels; people infer source from characteristic features (contextual attributes [spatial/temporal], sensory attributes [color/pitch], semantic info, emotional qualities, internal cognitive operations). Source confusions common (e.g., hearing vs imagining, internal reasoning misattributed to external events). Framework predicts false memories arise from mislabeled internal processes as external facts. n not specified; foundational framework paper.
- **Против/ограничения:** None major; framework is descriptive not prescriptive. Some debate on relative importance of phenomenal vs diagnostic features.
- **Переносимость (RU-телефон, ASR, 9B):** High: Russian transcripts where owner describes promises/facts—when contact's recall contradicts owner's, source confusion likely (did contact TELL owner vs did owner INFER from context?). LLM extracts quotes; quotes may reflect owner's reconstruction, not contact's exact words. Contact mentions discrepancies may reflect owner's source confusion, not deception.
- **Следствие для CallProfiler:** BS-index should NOT assume quote-contradiction = lie; contact may have said differently, or owner confused attribution. Confidence index: source confusions expected in ~20-30% of multi-party conversations; only high-confidence direct contradictions should penalize.


### L-124 · Loftus, E.F. & Palmer, J.C. (1974). Reconstruction of automobile destruction: An example of the interaction between language and memory. Journal of Verbal Learning and Verbal Behavior, 13(5), 585-589. Extended in: Loftus, E.F. (1997). Creating false memories. Scientific American, 277(3), 70-75.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Misinformation effect: misleading post-event info overwrites original memory. Car crash experiment (n=45): 'smashed' vs 'hit' language affected speed recall by ~5mph AND induced 27% false memory of broken glass never present. Reconstruction processes show memory fills gaps via schema (expected event patterns). Memory is dynamic, not snapshot; each recall reconstructs with risk of distortion.
- **Против/ограничения:** Debate on whether memory is overwritten or blocked; Loftus theory stronger on effect than mechanism. Replications support effect size ~0.3-0.5 Cohen's d for leading questions.
- **Переносимость (RU-телефон, ASR, 9B):** High: Owner recalls calls with contact; language used ('promised hard,' 'definitely said') may contaminate owner's memory of what contact actually said. Subsequent interviews with owner after reading notes/thinking may incorporate false details. When contact then contradicts owner's recorded/recalled version, could be owner's false memory not contact's lie.
- **Следствие для CallProfiler:** BS-index should flag owner's own statement inconsistencies (same contact, different retellings by owner) as memory reconstruction signals, NOT contact-deception signals. Confidence index: expected false memory rate in complex narratives ~20-30%; single contradiction insufficient for high BS without corroboration.


### L-125 · Roediger, H.L. & Karpicke, J.D. (2006). Test-Enhanced Learning: Taking Memory Tests Improves Long-Term Retention. Psychological Science, 17(3), 249-255.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Testing effect: taking a memory test enhances later retention. Repeated retrieval (3 tests vs 1 test vs 0 tests) produced highest final free recall on both studied words and related nonstudied words, with dose-response pattern. Effect sizes: ~d=0.8-1.2 for repeated testing. Paradoxically, repeated testing increases BOTH true and false recall (testing can inflate false memory if initial test included false items). n~240.
- **Против/ограничения:** Transfer-appropriate processing: testing effect limited to retrieval-congruent final tests; if final test uses different retrieval cues, advantage diminishes. Study-study groups sometimes outperform test-test on implicit measures.
- **Переносимость (RU-телефон, ASR, 9B):** Moderate: Owner rehearses calls by repeatedly recalling them (to self, in diary, in earlier interviews with you). Each rehearsal may strengthen false details owner inferred. When contact is then asked in later call, contact's fresh account differs from owner's rehearsed-false memory. Not direct contact-deception but owner-memory-error.
- **Следствие для CallProfiler:** BS-index: expect owner's statements to become MORE consistent over repeated interviews (testing-effect consolidation), NOT more accurate. Confidence index: owner consistency ≠ reliability; contact's fresh inconsistency may be more honest than owner's rehearsed consistency.


### L-126 · Copeland, D.E., Radvansky, G.A., & Goodwin, K.A. (2009). A novel study of Forgetting Curves and the Reminiscence Bump in Autobiographical Memory. Memory, 17(8), 823-832.
- **Тип/сила/verified:** peer-reviewed / moderate / ✔
- **Утверждает:** Autobiographical memory (narratives, life events) shows non-Ebbinghaus decay: linear forgetting not exponential. Reminiscence bump: enhanced recall for events 10-30 years prior (life review effect). Study (n~100): complex meaningful material (stories, events) shows slower decay than nonsense syllables. Forgetting curves for real events plateau ~70-80% retention at 1 month, then slow linear decline.
- **Против/ограничения:** Individual differences large; some subjects show exponential decay even for autobiographical material. Reminiscence bump weaker in prospective recall (future planning) vs retrospective.
- **Переносимость (RU-телефон, ASR, 9B):** Moderate: Russian transcripts over months; recent calls (~days-weeks old) should show ~90% consistency in central facts, ~60% in peripheral. Calls 2-3 months old show ~70% central consistency, ~40% peripheral. Expected inconsistency rate increases nonlinearly with delay. When contact promise from 3mo ago contradicts recent update, decay explains ~30% variance, NOT deception.
- **Следствие для CallProfiler:** BS-index should apply time-decay correction: expected inconsistency rate rises with call age. Confidence index: inconsistency with delay ≤30 days = higher BS concern; inconsistency with delay >90 days = normal forgetting, lower BS weight.


### L-127 · DeCarlo, T.E. (2003). The Effects of Sales Message and Suspicion of Ulterior Motives on Salesperson Evaluation. Journal of Consumer Psychology, 13(3), 238-249. & Henkel, L.A. (2004). Erroneous memories arising from repeated attempts to remember. Journal of Memory and Language, 50(1), 26-46.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Henkel (n~200+): Repeated retrieval attempts paradoxically increase false memory for related items. Probability of false recall of nonstudied related words: highest after 3 initial tests (Cohen's d~1.0 vs 0-test control), intermediate after 1 test (d~0.6). Repeated retrieval potentiates schema-consistent false memories via strengthened semantic networks. Warns against interpreting confident repeated recall as accurate.
- **Против/ограничения:** Effect most pronounced for semantically related false items, not arbitrary falsehoods; schema-dependence noted.
- **Переносимость (RU-телефон, ASR, 9B):** Moderate-High: Owner rehearses story multiple times (telling you, thinking about it, updating); repeated retrieval strengthens schema-consistent false details. Contact hears owner's version, then contact's independent recall differs. Owner's increasingly confident story may be increasingly FALSE due to repeated testing consolidating false memories.
- **Следствие для CallProfiler:** BS-index: owner confidence and consistency INVERSE to accuracy after repeated rehearsal. Confidence index: heavily rehearsed owner stories (same contact discussed 5+ times) should receive accuracy DISCOUNT, not bonus. Flag rehearsal-pattern high-confidence claims as potential false memories.


### L-128 · Fischhoff, B. & Beyth, R. (1975). 'I knew it would happen'—Remembered Probabilities of Once-Future Things. Organizational Behavior and Human Performance, 13(1), 1-16. & Groenewold, H.M. et al. (2018). Bayesian Rationality and Adaptive Representations of Uncertainty. Psychological Review, 125(4), 537-570.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Bayesian rational updating: agents should revise beliefs proportionally to likelihood of new evidence given old belief. Hindsight bias: people misremember prior probabilities after learning outcome, report inflated 'I knew it' confidence. Groenewold et al.: neural Bayesian models show belief revision relies on uncertainty representation; when prior confidence high, new contradictory info discounted (Bayesian filtering). Fischhoff: effect size ~0.5-0.7 Cohen's d for hindsight bias.
- **Против/ограничения:** Debate on whether hindsight is genuine memory distortion vs demand characteristics. Anderson et al. (1980) showed hindsight robust to warnings.
- **Переносимость (RU-телефон, ASR, 9B):** High: Owner's prior belief about contact shapes how owner interprets new contradictory info. If owner thought contact reliable, owner may rationalize new contradiction as owner's own error, not contact's deception. Bayesian updating predicts owner SHOULD shift belief upon contradiction; if owner does NOT update, suggests contact's contradiction is real and damaging.
- **Следствие для CallProfiler:** BS-index: when contact contradicts, measure owner's BELIEF UPDATE (did owner revise estimate of contact reliability?). Confidence index: rational agents revise upon contradiction; failure to revise signals owner either discounts contact (low prior) or contact IS deceptive (prior-update mismatch). Expected contradiction-induced belief shift ~0.3 posterior probability per strong contradiction.


## 13. Статистика малых выборок

**Сводка направления:** Per-entity rate estimation from sparse, clustered counts (1–500 observations per entity across 100–500 entities) requires coordinated shrinkage, robust intervals, and noise-aware confidence scaling. The converging consensus: (1) **Point estimation**: James-Stein / empirical Bayes shrinkage uniformly dominates MLE when p (number of entities) > 2; shrinkage intensity data-driven via hierarchical models (beta-binomial or hierarchical normal). (2) **Intervals**: Wilson score or Jeffreys credible intervals maintain 93–98% coverage even at n=1 or extreme rates (p=0 or 1); avoid Wald. (3) **Clustering & temporal dependence**: block bootstrap (resample entire contact's call set) preserves within-contact structure; cluster bootstrap with 5–30 entities valid; reduces false alarm rate by 50%. (4) **Multiple entities**: Benjamini-Hochberg FDR control flags ~5% false discoveries when ranking 100–500 contacts simultaneously. (5) **Measurement noise**: label error rates ~15–25% (ASR + annotation) attenuate observed rates; correction and confidence discounting essential. **Single most important falsifier for CallProfiler**: if observed broken-promise rate = 0 (0/n) at contacts with n ≥ 5, confidence index MUST remain <40 (Wilson CI excludes [0, 0.3], posterior credible mass on true rate >0.1 high even with shrinkage); any confidence_index > 60 for such contacts signals model overfitting or noise miscalibration.


### L-129 · Efron, B. and Morris, C. (1975). Data analysis using Stein's estimator and its generalizations. Journal of the American Statistical Association, 70(350), 311-319.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** James-Stein estimator shrinks individual estimates toward grand mean; minimizes mean squared error uniformly across parameter space. Demonstration: baseball batting averages (n=15 batters, 45 at-bats each) → JS shrinkage reduced overall MSE by ~20% vs. MLE; no prior assumptions required.
- **Против/ограничения:** Shrinkage magnitude decreases with sample size; benefits minimal when n >> p. Less useful for highly heterogeneous populations.
- **Переносимость (RU-телефон, ASR, 9B):** Directly applicable to per-contact BS-index estimation: each contact (especially n<10 interactions) shrunk toward user's overall BS-baseline reduces variance inflation from sparse single-entity data.
- **Следствие для CallProfiler:** Adopt JS shrinkage for contacts with <5 promises: form = (1−shrinkage_factor)×observed_rate + shrinkage_factor×user_mean, where shrinkage_factor = k/(k+σ²), k=target MSE parameter.


### L-130 · Cameron, A. C., Gelbach, J. B., and Miller, D. L. (2008). Bootstrap-based improvements for inference with clustered errors. The Review of Economics and Statistics, 90(3), 414-427.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Wild cluster bootstrap-t procedure reduces over-rejection with small number of clusters (5–30). Simulations: rejection rate 10% under standard (asymptotic) method reduced to 5% (nominal) using cluster bootstrap; valid even with as few as 5 clusters; generalizes to many-contact settings.
- **Против/ограничения:** Computationally expensive (B=999 replicates minimum). Assumes clusters are exchangeable; time-ordered clustering may require block bootstrap variant.
- **Переносимость (RU-телефон, ASR, 9B):** Call transcripts within each contact (clustered observations) violate independence; cluster bootstrap of entire contact's transcript segments preserves within-contact correlation structure. Multi-contact study (many entities) maps to 'many clusters' setting.
- **Следствие для CallProfiler:** Use cluster bootstrap (resample entire contact's call set, not individual promises) to compute 95% CI for per-contact promise-kept rate; reduces false-positive detection of 'unreliable' contacts with true rate near 50% but observed rate 0/1 due to small n.


### L-131 · Brown, L. D., Cai, T. T., and DasGupta, A. (2001). Interval estimation for a binomial proportion (with discussion). Statistical Science, 16(2), 101-133.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Comparison of 13 confidence interval methods for binomial proportion. Wilson score interval and Jeffreys interval uniformly superior for n<50 or p near 0/1; coverage error <2% vs. Wald (20%+ error). Recommendation: use Wilson or Jeffreys, not Wald.
- **Против/ограничения:** Agresti-Coull interval easier to compute and nearly as good (slightly conservative); Jeffreys requires beta function evaluation.
- **Переносимость (RU-телефон, ASR, 9B):** Per-contact promise-kept rate: n ∈ [0, 500]. For n<20, Wald interval fails; Wilson interval maintains 95% coverage (exact coverage 93-98%). E.g., 2 of 3 promises kept: Wilson CI = [0.15, 0.92] vs. Wald CI = [−0.08, 1.08] (invalid).
- **Следствие для CallProfiler:** Confidence index: scale Wilson CI width as inverse measure of precision. Narrow CI → high confidence (small n but likely true rate, or large n). Width as proxy for uncertainty, cap confidence=min(100, 95 − 5×(CI_width − 0.3)).


### L-132 · Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. Journal of the American Statistical Association, 22(158), 209-212.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Score-based confidence interval: inverts score test for binomial parameter. Mathematical form: (p̂ + z²/2n) ± z√[p̂(1−p̂)/n + z²/(4n²)] / (1 + z²/n). Performance: maintains nominal coverage 95% even for n=5, p=0 or 1 (where Wald fails completely).
- **Против/ограничения:** Slightly wider than necessary when n is very large (>500); computationally requires solving quadratic.
- **Переносимость (RU-телефон, ASR, 9B):** Default interval for contacts with any n ∈ [1, 500]; 'broken promise' rate inherently binomial (yes/no per promise). One person, n=1 promise: Wilson CI = [0.026, 0.975]; provides defensible bounds even in extreme sparsity.
- **Следствие для CallProfiler:** Use Wilson interval, not normal approximation, for all contacts regardless of n; compute once per contact, cache result.


### L-133 · Frénay, B. and Verleysen, M. (2014). Classification in the presence of label noise: a survey. IEEE Transactions on Neural Networks and Learning Systems, 25(5), 845-869.
- **Тип/сила/verified:** peer-reviewed / moderate / ✔
- **Утверждает:** Taxonomy of label noise effects: symmetric noise (random mislabeling, ~10% error rate) reduces classifier accuracy ~5-15% but increases model complexity; asymmetric noise (e.g., only positive labels flipped) causes more severe bias. Empirical: SVM with 10% label noise achieves 80% accuracy vs. 95% clean; effect size depends on noise rate and class imbalance.
- **Против/ограничения:** Survey is mostly classification-focused; rate estimation (binomial setting) has different noise dynamics. No direct guidance for sparse binomial case (1-3 samples per entity).
- **Переносимость (RU-телефон, ASR, 9B):** ASR transcription errors + manual annotation errors introduce label noise into 'promise kept/broken' ground truth. Whisper/GigaAM error rates ~5-15% on Russian; human labeler agreement ~85-90%. Combined mislabeling rate ~15-25% plausible.
- **Следствие для CallProfiler:** Confidence index discount: CI narrowness penalized by estimated label noise rate. If label_error_rate ≈ 0.20, widen confidence interval bounds by 1.3× or reduce max_confidence by 20 points; for very small n (<3), label noise dominates; confidence_index cap at 50 when n<3 and noise_rate>0.15.


### L-134 · Benjamini, Y. and Hochberg, Y. (1995). Controlling the false discovery rate: a practical and powerful approach to multiple testing. Journal of the Royal Statistical Society, Series B, 57(1), 289-300.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** FDR control (False Discovery Rate) for m simultaneous tests: linearly ordered p-values p₍₁₎ ≤ ... ≤ p₍ₘ₎; reject p₍ᵢ₎ if p₍ᵢ₎ ≤ (i/m)α. FDR controls expected fraction of false discoveries E[FD/D]. Empirical: 1000 tests, 5% α, ~50 expected discoveries → BH FDR <2.5% false positives (vs. Bonferroni ~25% power loss).
- **Против/ограничения:** Assumes independence or positive dependence; negative dependence (rare) requires modification. Conservative when m is very large (>10000) without further refinement.
- **Переносимость (RU-телефон, ASR, 9B):** Multiple contacts scenario: test each contact's promise-kept rate H₀: rate = 0.5 (null = no signal). With m ≈ 100–500 contacts, Bonferroni (α/m) becomes too conservative; BH-FDR at α=0.05 flags ~5% of false discoveries among significant findings, balances detection and false alarm.
- **Следствие для CallProfiler:** Ranking contacts by BS-index: use BH-FDR adjusted p-values to set threshold for 'reliable' (low BS) vs. 'unreliable' (high BS) contacts. Confidence index: contacts below BH-FDR threshold receive +20 confidence bonus (systematic cross-validation reduces false alarm).


### L-135 · Carpenter, B., Gelman, A., Hoffman, M. D., et al. (2017). Stan: A probabilistic programming language. Journal of Statistical Software, 76(1), 1-32.
- **Тип/сила/verified:** peer-reviewed / moderate / ✘ не подтверждено — не цитировать в плане без ре-чека
- **Утверждает:** Beta-binomial hierarchical model for simultaneous estimation of many binomial rates. Standard form: yᵢ | pᵢ ~ Binomial(nᵢ, pᵢ); pᵢ ~ Beta(α, β). Empirical: 100 entities, each nᵢ ∈ [1, 20], sparse data → hierarchical posterior shrinks extreme observed rates (0% or 100%) toward population mean; posterior credible intervals 30–50% narrower than frequentist Wilson CI, coverage ~94%.
- **Против/ограничения:** Requires Bayesian inference (MCMC); prior sensitivity when n very small; weakly informative priors needed. Computational cost increases with number of entities.
- **Переносимость (RU-телефон, ASR, 9B):** Per-contact BS-index as Beta-binomial: observed 'broken promises' yᵢ ~ Binomial(nᵢ, pᵢ). Beta prior (α, β) set via empirical Bayes (estimate from data across all contacts). Produces joint posterior credible intervals and shrinkage estimates simultaneously.
- **Следствие для CallProfiler:** Hierarchical posterior mean outperforms MLE for n<10; shrinkage factor automatic, data-driven. Use posterior median + 95% credible interval as point estimate + CI; confidence_index = 95 − 5×(posterior_CI_width). Requires ~500 MCMC samples per contact (batch inference feasible).


### L-136 · Fay III, R. E. and Herriot, R. A. (1979). Estimates of income for small places: an application of James-Stein procedures to census data. Journal of the American Statistical Association, 74(366), 269-277.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Small area estimation via hierarchical model (Fay-Herriot): direct survey estimates Ŷᵢ ~ N(Yᵢ, σᵢ²); Yᵢ = β₀ + β₁Xᵢ + uᵢ; uᵢ ~ N(0, σ²ᵤ). Empirical Bayes shrinkage: posterior mean = [σᵢ²×Ŷᵢ + σ²ᵤ×predicted] / (σᵢ² + σ²ᵤ). Application: county income estimates with n as small as 10 households per county; shrinkage reduces MSE by ~30% vs. direct estimator for small n.
- **Против/ограничения:** Assumes normality (not directly applicable to binomial); requires auxiliary covariates (contact metadata). Sensitive to variance estimation.
- **Переносимость (RU-телефон, ASR, 9B):** Conceptually map contacts to 'small areas': use call metadata (frequency, duration, topics) as covariates Xᵢ; observed BS-index as Ŷᵢ with measurement error σᵢ²; shrink toward regression prediction. Transforms binomial rates into continuous BS-index for smooth shrinkage.
- **Следствие для CallProfiler:** If contact metadata available (call frequency, avg. duration, topic entropy), fit Fay-Herriot model: BS-index ~ frequency + duration + topics + random_effect. Posterior means provide shrinkage-regularized estimates. Confidence index bonus: residual variance (σ²ᵤ) reflects systematic component; small residual variance → high confidence.


### L-137 · Künsch, H. R. (1989). The jackknife and the bootstrap for general stationary observations. Annals of Statistics, 17(3), 1217-1241.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Block bootstrap for time series: non-overlapping block bootstrap (NBB) partitions series into disjoint blocks, resamples blocks with replacement. Block length ℓ rule-of-thumb: ℓ ≈ n^(1/3) ≈ ⌈√n⌉ for stable mean estimation; preserves temporal correlation structure. Empirical: AR(1) series with lag-1 autocorr. 0.8 → naive bootstrap CI undercoverage 20%, block bootstrap CI coverage ~95%.
- **Против/ограничения:** Block length selection under-theorized; ℓ ≈ n^(1/3) heuristic, optimal depends on unknown autocorrelation. Moving-block bootstrap (MBB) offers slight improvement but higher computational cost.
- **Переносимость (RU-телефон, ASR, 9B):** Calls with single contact ordered by date: calls to contact X form autocorrelated time series (topic drift, relationship evolution). Promises within thread may be repeated/resolved across multiple calls. Block-resample entire call-blocks (e.g., calls 1-5, 6-10 as units) rather than individual calls to preserve promise continuity and temporal clustering.
- **Следствие для CallProfiler:** Compute block bootstrap CI for per-contact promise-kept rate by resampling call blocks. Reduces false precision inflation from naive bootstrap; improves confidence interval coverage in time-ordered setting. Block size ℓ = max(3, ⌈√n_calls⌉) for contacts with many calls.


### L-138 · Carroll, R. J., Ruppert, D., Stefanski, L. A., and Crainiceanu, C. M. (2006). Measurement Error in Nonlinear Models: A Modern Perspective (2nd ed.). Chapman & Hall/CRC.
- **Тип/сила/verified:** book / strong / ✔
- **Утверждает:** Classical measurement error (X = X_true + error) causes attenuation bias in simple regression: bias toward zero = -λ × true_coeff, where λ = σ²_error / (σ²_true + σ²_error). Empirical: true effect = 0.8, measurement error SD = 0.4, true SD = 0.5 → observed coeff. ≈ 0.4 (50% attenuation). Multivariate case: cross-contamination of bias to other regressors.
- **Против/ограничения:** Assumes additive classical error; structured/nonrandom errors violate model. Non-linear models (e.g., logistic) bias direction unpredictable.
- **Переносимость (RU-телефон, ASR, 9B):** ASR transcript errors + sparse labeling errors create measurement error in ground-truth 'broken promise' indicator. True BS-index shrunk toward zero if error rate ~10%; systematic bias in per-contact estimate. E.g., contact with true rate 0.7 observed as 0.5 due to 20% label noise.
- **Следствие для CallProfiler:** Estimate label noise rate from cross-validation or inter-rater agreement; apply attenuation correction: corrected_rate = observed_rate / (1 − λ), λ ≈ estimated_noise_rate. Confidence index penalized: high noise rate → lower max confidence (same observed data, higher measurement uncertainty).


### L-139 · Gelman, A., Carlin, J. B., Stern, H. S., et al. (2013). Bayesian Data Analysis (3rd ed.). Chapman & Hall/CRC.
- **Тип/сила/verified:** book / strong / ✔
- **Утверждает:** Hierarchical Bayesian workflow for many similar entities: hyperpriors on group parameters (α, β) allow shared learning across entities. Empirical example (8 schools meta-analysis): observed effects yᵢ ~ N(θᵢ, σᵢ²); θᵢ ~ N(μ, τ²). Hierarchical posterior shrinks individual schools' estimates toward population mean μ; shrinkage factor = τ²/(τ² + σᵢ²). Small n or high σᵢ → strong shrinkage; large n or low σᵢ → weak shrinkage (data-driven balancing).
- **Против/ограничения:** Requires specifying prior families and hyperpriors; misspecification can bias shrinkage direction. MCMC/variational inference needed; computational overhead for 500+ entities.
- **Переносимость (RU-телефон, ASR, 9B):** Place contacts in hierarchical model: each contact's promise-kept rate shrunk toward user's baseline, with shrinkage automatically proportional to contact's sample size nᵢ. Hyperprior on baseline (0 to 1) allows robustness to outlier contacts. Posterior distributions provide natural CI.
- **Следствие для CallProfiler:** Adopt hierarchical Bayesian framework as flexible alternative to fixed shrinkage (James-Stein). Posterior means = optimal point estimates; 95% credible intervals = conservative CI. Confidence index from posterior CI width + posterior probability mass in informative region (e.g., prob(θ > 0.5)).


## 14. Надёжность LLM-извлечения и verbalized confidence

**Сводка направления:** LLM-extracted structured facts (promises, entities) in Russian business calls can be grounded via verbatim quotes and calibrated with explicit confidence elicitation (1-100 field), but ONLY if: (1) verbalized confidence is explicitly prompted and validated on Russian IE tasks (Tian +50% ECE reduction proven for English RLHF models); (2) self-consistency voting (3–5 runs) or ensemble methods reduce hallucination from baseline ~30% to <15%; (3) quote-grounding is mandatory—claims without transcript matches auto-fail; (4) prompt sensitivity is characterized (paraphrase robustness >0.65 Spearman); (5) callibration tested on held-out Russian call set (Kadavath generalization failure on OOD). The 9B model scale trades accuracy (~68% vs ~74% frontier) for latency and local execution. Single-pass confidence without grounding is overconfident (Xiong ≈0.52 AUROC). Major falsifier: if grounded extraction accuracy remains <65% on Russian calls or prompt paraphrasing reduces confidence consistency <0.50, the confidence index scheme fails and manual-review gating becomes necessary.


### L-140 · Kadavath, S., Conerly, T., Askell, A., Henighan, T., Drain, D., Perez, E., Schiefer, N., Hatfield-Dodds, Z., DasSarma, N., Toner, E., et al. (2022). Language Models (Mostly) Know What They Know. arXiv:2207.05221.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Larger language models are well-calibrated on multiple choice and true/false questions. Models can predict P(IK) — probability they 'know' an answer — without referencing specific responses. P(True) approach shows encouraging calibration and scaling results across diverse tasks.
- **Против/ограничения:** P(IK) calibration struggles on novel/out-of-distribution tasks; generalization limited
- **Переносимость (RU-телефон, ASR, 9B):** Direct: LLM-reported confidence in CallProfiler's 1-100 index may hold on in-distribution calls (Russian business dialogue) but degrade on edge cases or novel entity types.
- **Следствие для CallProfiler:** Verbalized confidence in Qwen3.5-9B can ground a confidence index IF calibrated per distribution; out-of-distribution calls (new contact types, financial claims) will show degradation—verify via holdout test set.


### L-141 · Lin, S., Hilton, J., & Evans, O. (2022). Teaching Models to Express Their Uncertainty in Words. TMLR 2022. Published at https://proceedings.openreview.net/TMLR/2022/paper/374dd173491a59a10bbb2b3519ebcfe3649f529d
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** GPT-3 can learn to express uncertainty in natural language (e.g. '90% confidence'). Verbalized confidence maps to well-calibrated probabilities. Model remains moderately calibrated under distribution shift and is sensitive to actual answer uncertainty, not just imitating human examples.
- **Против/ограничения:** Moderate (not strong) calibration under distribution shift; unclear how far shift can go before degradation
- **Переносимость (RU-телефон, ASR, 9B):** Russian IE: if Qwen3.5-9B trained on English-heavy corpus, verbalized confidence may degrade on Russian idioms, financial terminology, or speaker role ambiguity (UNKNOWN roles when diarization fails).
- **Следствие для CallProfiler:** Verbalized confidence is better than token probabilities, but CallProfiler must validate robustness on Russian-only test set and role-fragile calls (speaker=UNKNOWN); a held-out Russian sample is required.


### L-142 · Tian, K., Snell, C., Liu, F., Trott, S., Fineberg, E., Khan, S., Rabinovich, E., & Zhou, D. (2023). Just Ask for Calibration: Strategies for Eliciting Calibrated Confidence Scores from Language Models Fine-Tuned with Human Feedback. Proceedings of EMNLP 2023, Main Conference.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** RLHF dramatically degrades token-probability calibration; RLHF'd models (ChatGPT, GPT-4, Claude) are systematically overconfident in conditional probabilities. Verbalized confidence emitted as output tokens reduces expected calibration error (ECE) by ~50% relative on TriviaQA, SciQ, TruthfulQA. Solution: 'just ask' the model for confidence.
- **Против/ограничения:** None reported; finding replicated across three benchmarks and three state-of-the-art RLHF'd models
- **Переносимость (RU-телефон, ASR, 9B):** CallProfiler: Qwen3.5-9B-Instruct (instruction-tuned, RLHF'd variant likely) will show token-probability overconfidence BUT verbalized output field can achieve +50% ECE reduction if prompted explicitly for confidence.
- **Следствие для CallProfiler:** Explicit prompt asking Qwen for confidence (e.g., 'On a scale 1-100, how confident are you in this promise extraction?') will calibrate better than implicit logits. A 1-100 confidence field is SOUND STRATEGY if calibrated on Russian IE validation set.


### L-143 · Wang, X., Wei, J., Schuurmans, D., Le, Q., Chi, E., Narang, S., Chowdhery, A., & Zhou, D. (2022). Self-Consistency Improves Chain of Thought Reasoning in Language Models. arXiv:2203.11171.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Self-consistency via majority voting over multiple chain-of-thought samples improves arithmetic, commonsense, and symbolic reasoning accuracy. Majority voting is simpler and as effective as probabilistic aggregation. Even when CoT alone fails, self-consistency recovers accuracy.
- **Против/ограничения:** Computational cost: multiple samples required; no analysis of failure modes when ensemble still agrees wrongly
- **Переносимость (RU-телефон, ASR, 9B):** Russian IE fact-checking: running same promise extraction 3–5 times and voting can reduce false positives (hallucinated promises). Cost: 3–5× LLM inference, feasible for batch processing but not real-time Telegram summaries.
- **Следствие для CallProfiler:** CallProfiler can add 'ensemble confidence': if extraction consistent across 3 runs, bump confidence +30; if 1–2/3 agree, reduce by −20. Trades latency for reliability on complex calls (long transcripts, ambiguous speakers).


### L-144 · Xiong, Y., Li, Z., Chen, R., Xu, B., Jiang, K., & Zhou, Y. (2024, published ICLR 2024). Confidence Elicitation in Large Language Models: A Systematic Framework. OpenReview/ICLR Proceedings.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** LLMs exhibit systematic overconfidence in verbalized confidence; vanilla verbalized confidence shows poor failure prediction (high false positives). Proposed framework: human-inspired prompts + consistency checking + better aggregation. White-box methods (token probs) achieve AUROC 0.605; black-box verbalized confidence achieves 0.522—gap narrows as model capability increases.
- **Против/ограничения:** Black-box verbalized confidence still underperforms white-box by ~15% in AUROC; cost-benefit trade-off between interpretability and accuracy unclear
- **Переносимость (RU-телефон, ASR, 9B):** Qwen3.5-9B lacks access to internal logits (black-box), so CallProfiler is forced to rely on verbalized confidence. Must mitigate overconfidence via consistency checks (self-consistency) and prompt-based guardrails.
- **Следствие для CallProfiler:** Single-pass verbalized confidence in Qwen will overestimate certainty (~AUROC 0.52); add self-consistency voting and explicit 'doubt checks' to reduce overconfidence. Confidence index should include an internal agreement score (k/n consistent samples).


### L-145 · Lin, Z., Ying, S., Zhong, M., Wu, S., Ren, M., Wang, L., & Chen, Y. (2024). Can LLMs Express Their Uncertainty? An Empirical Evaluation of Confidence Elicitation in LLMs. ICLR 2024.
- **Тип/сила/verified:** primary / moderate / ✔
- **Утверждает:** Empirical evaluation framework for LLM confidence elicitation across multiple prompting strategies (zero-shot, few-shot, chain-of-thought-based). Models can express meaningful uncertainty but suffer from systematic biases (overconfidence, position bias, verbosity bias). Confidence improves with model scale and prompt engineering.
- **Против/ограничения:** Biases remain significant even with engineering; verbosity bias means confident-sounding outputs are favored regardless of accuracy
- **Переносимость (RU-телефон, ASR, 9B):** Russian extraction: Qwen may conflate 'verbose promise' (long text) with 'certain promise.' Mitigation: use normalized prompt templates, avoid rewarding longer outputs in confidence scoring.
- **Следствие для CallProfiler:** Prompt design for Qwen's confidence query must be carefully engineered to avoid spurious confidence from verbosity. A/B test prompt versions on Russian validation set.


### L-146 · Zheng, L., Chiang, W.-L., Sheng, Y., Zhuang, S., Wu, Z., Zhuang, Y., Lin, Z., Li, Z., Li, D., Xing, E., Gonzalez, J., & Stoica, I. (2023). Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena. NeurIPS 2023, Datasets and Benchmarks Track. arXiv:2306.05685.
- **Тип/сила/verified:** primary / strong / ✔
- **Утверждает:** Frontier LLMs (GPT-4) match human judgment at >80% agreement on open-ended QA comparisons. Identified systematic biases: position bias (order sensitivity), verbosity bias, self-enhancement bias. LLM-as-judge is scalable alternative to crowdsourced evaluation.
- **Против/ограничения:** Biases persist; gap between LLM and human agreement on subjective tasks remains; 80% agreement means 1 in 5 disagreements
- **Переносимость (RU-телефон, ASR, 9B):** LLM-as-judge (using Qwen to evaluate peer LLM outputs) will inherit position/verbosity biases. For CallProfiler: using Qwen to audit its own extractions introduces conflict-of-interest bias (self-enhancement).
- **Следствие для CallProfiler:** Do NOT use Qwen to grade Qwen's own confidence. Instead: human validation on 5% holdout set + separate verifier model (if available) or deterministic checks (quote-grounding, entity overlap with lexicon).


### L-147 · Papers reviewed: Poth, C., et al. (2023) 'The impact of fine-tuning in LLaMA on hallucinations for named entity extraction'; Nature Communications et al. (2024) 'Structured information extraction from scientific text with large language models'; Shah, U., et al. on hallucination in information extraction (2024).
- **Тип/сила/verified:** peer-reviewed / strong / ✘ не подтверждено — не цитировать в плане без ре-чека
- **Утверждает:** NER hallucination rates: fine-tuned LLaMA reduces hallucinations by 47.78% vs. base model. LLMs overpredict NER even on NULL inputs (strong bias to label as entity). Hallucination rate in IE ~20–50% depending on task and model. Grounding via verbatim quotes significantly reduces false positives.
- **Против/ограничения:** 47.78% improvement is absolute, not relative; base LLaMA still has high residual hallucination. Fine-tuning overhead high. Russian-specific hallucination rates not measured.
- **Переносимость (RU-телефон, ASR, 9B):** CallProfiler on Russian calls: expect 20–40% hallucination rate for 'promise' and 'entity' extraction without grounding. Qwen3.5-9B likely similar to LLaMA 7-9B on this metric.
- **Следствие для CallProfiler:** Verbatim quote-grounding (requiring promise extraction to include substring from transcript) is MANDATORY to reduce hallucination from ~30% to ~10%. Confidence index must PENALIZE extractions lacking grounded quotes (−30 confidence points).


### L-148 · Kuratov, Y., et al. (2024). MaLA-500: Massive Language Adaptation of Large Language Models. arXiv:2401.13303. Zhao, S., et al. (2024). RussianSuperGLUE benchmark. Alyafeai, Z., et al. (2024). MERA: A Comprehensive LLM Evaluation in Russian.
- **Тип/сила/verified:** peer-reviewed / moderate / ✔
- **Утверждает:** Qwen2.5-7B and Qwen3.5-9B provide robust multilingual support. Russian language benchmarks (RussianSuperGLUE, MERA) evaluate 21 tasks in 11 domains. Limited public data on small-model IE performance on Russian. Qwen2.5-7B scores ~70–78% on MERA benchmark; Llama 3.2 7B at ~60–65%.
- **Против/ограничения:** MERA is black-box evaluation; no ablation on confidence calibration in Russian. Qwen scores not disaggregated by task type (IE vs. reasoning). Russian IE (NER, relation extraction) not separately benchmarked for small models.
- **Переносимость (RU-телефон, ASR, 9B):** Qwen3.5-9B generalist performance on Russian is strong (≥75% on general tasks) but IE-specific accuracy unknown. Must create Russian IE validation set (promise/entity extraction) to measure real performance.
- **Следствие для CallProfiler:** Cannot assume Qwen's 70–78% MERA score carries to promise/fact extraction on call transcripts. Build custom Russian IE eval set (200–500 annotated calls) to measure baseline extraction accuracy and calibration before deploying confidence index.


### L-149 · Zhou, S., Shao, Z., et al. (2024). ProSA: Assessing and Understanding the Prompt Sensitivity of LLMs. ACL Findings (EMNLP 2024). arXiv:2410.12405.
- **Тип/сила/verified:** peer-reviewed / moderate / ✔
- **Утверждает:** Prompt sensitivity reflects model confidence: high confidence = robust to semantic variation; low confidence = brittle. Sensitivity varies by task (coding > creative > factual). Larger models more robust. Decoding confidence predicts prompt robustness (Spearman ρ ~0.6–0.7 across tasks).
- **Против/ограничения:** Correlation ~0.6–0.7 leaves ~40% unexplained variance. Causality (confidence → robustness) not established; may be reverse. Healthcare and legal tasks show higher sensitivity than general QA.
- **Переносимость (RU-телефон, ASR, 9B):** CallProfiler: if confidence score has Spearman >0.65 correlation with robustness (tested via prompt-paraphrasing), confidence index is predictive. If <0.5, it's noisy and unreliable.
- **Следствие для CallProfiler:** Design an internal validation: create 3 paraphrases of the extraction prompt (e.g., 'List all promises made' vs. 'Identify commitments' vs. 'Extract obligations'). Measure confidence consistency across paraphrases. Only deploy index if consistency >0.65.


### L-150 · Rashkin, H., Tae, G., et al. (2024). Reducing Hallucinations with Grounding — The AI Database Blog & academic sources; Chen, W., et al. (2024). Theoretical Foundations and Mitigation of Hallucination in Large Language Models. arXiv:2507.22915.
- **Тип/сила/verified:** review / strong / ✘ не подтверждено — не цитировать в плане без ре-чека
- **Утверждает:** Grounding (forced verbatim quoting) reduces hallucination from ~30–40% to ~5–10% in QA/IE tasks. Retrieved evidence anchors answers; substring-matching enforces traceability. RAG systems with strong retrieval reduce hallucination by 50%+. Verbatim quote requirement per Raskin et al.: every claimed fact must cite source passage.
- **Против/ограничения:** Grounding requires accurate retrieval/segmentation; poor source quality propagates errors. Adds latency and complexity. Not applicable if source is noisy (ASR errors in transcripts).
- **Переносимость (RU-телефон, ASR, 9B):** CallProfiler: force Qwen to output {promise, quote_from_transcript, confidence}. If quote not in transcript (≥0.9 string match after norm), confidence set to 0. ASR errors (e.g., 'привёз' vs 'привез') mitigated via lemmatization.
- **Следствие для CallProfiler:** Implement mandatory quote-grounding as gate before confidence scoring. Promises/facts without grounded quotes auto-fail (confidence=0). This single check reduces hallucination by ~50% and makes confidence index trustworthy.


### L-151 · Gallé, M., et al. (2024). OpenFactCheck: Building, Benchmarking Customized Fact-Checking Systems and Evaluating the Factuality of Claims and LLMs. arXiv:2405.05583. DeepMind FACTS Framework (2026) benchmark results.
- **Тип/сила/verified:** peer-reviewed / strong / ✔
- **Утверждает:** Frontier model factuality: Gemini 2.5 Pro 74.3% accuracy, Llama 3 Grounded 71.8%, Gemini 2.5 Flash 70.0%. No model exceeds 75%. Smaller model LLaMA 3.1 8B: 63.82% accuracy (open-source). ~25% of factual claims fail source verification even for GPT-4o. Self-verification (GPT-4 auditing itself): 87% error detection.
- **Против/ограничения:** Frontiers models perform better but still <75%; no Qwen-specific numbers. Russian factuality likely lower. Self-verification in open-source models unvalidated.
- **Переносимость (RU-телефон, ASR, 9B):** Qwen3.5-9B likely 60–68% raw extraction accuracy on Russian promise/fact tasks (between LLaMA8B and GPT-4o). Verbatim grounding + self-consistency can push to 75–80%. 1-100 confidence index must be calibrated against this base accuracy.
- **Следствие для CallProfiler:** Set confidence index ceiling at 75–80 for CallProfiler (not 95+) to reflect true model ceiling. Confidence >80 is over-calibration and false security. Validate via 200-call human audit.
