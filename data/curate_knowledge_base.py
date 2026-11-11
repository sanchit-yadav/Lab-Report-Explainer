"""Curates verified clinical reference documents from MedlinePlus and public health sources.

Generates 30 patient-facing clinical education documents covering the top
routine laboratory tests, complete with source URLs and structured metadata.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAG_SOURCES_DIR = PROJECT_ROOT / "data" / "rag_sources"

DOCUMENTS: List[Dict[str, Any]] = [
    # --------------------------------------------------------------------------
    # Complete Blood Count (CBC)
    # --------------------------------------------------------------------------
    {
        "test_name": "Hemoglobin",
        "category": "Complete Blood Count",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/hemoglobin-test/",
        "content": (
            "What the Test Measures:\n"
            "Hemoglobin is an iron-rich protein in your red blood cells that carries oxygen from your lungs "
            "to the rest of your body and returns carbon dioxide to your lungs to be exhaled.\n\n"
            "What Elevated / High Values Mean:\n"
            "High hemoglobin levels (polycythemia) may be linked to dehydration, smoking, living at high altitudes, "
            "chronic lung diseases (such as COPD), congenital heart defects, or certain bone marrow disorders.\n\n"
            "What Low Values Mean:\n"
            "Low hemoglobin indicates anemia. Common causes include iron deficiency, vitamin B12 or folate deficiency, "
            "chronic kidney disease, heavy menstrual bleeding, internal blood loss, or bone marrow suppression.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- What is the likely reason my hemoglobin is outside the standard reference range?\n"
            "- Do I need additional iron studies, ferritin, or vitamin B12 testing?\n"
            "- Should we retest in 4 to 8 weeks to check for stabilization?"
        ),
    },
    {
        "test_name": "White Blood Cell Count (WBC)",
        "category": "Complete Blood Count",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/white-blood-count/",
        "content": (
            "What the Test Measures:\n"
            "White blood cells (leukocytes) are a vital component of your immune system that defend against bacterial, "
            "viral, fungal, and parasitic infections, and play a key role in inflammatory responses.\n\n"
            "What Elevated / High Values Mean:\n"
            "An elevated WBC count (leukocytosis) most commonly indicates an active bacterial or viral infection, "
            "tissue damage, severe physical stress, inflammatory conditions (e.g. rheumatoid arthritis), smoking, "
            "or, less commonly, bone marrow disorders.\n\n"
            "What Low Values Mean:\n"
            "A low WBC count (leukopenia) suggests an increased susceptibility to infection. Potential causes include "
            "viral infections that suppress bone marrow, autoimmune disorders (like lupus), bone marrow damage, "
            "or severe overwhelming infections.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- Does my elevated or reduced white count suggest an active or resolving infection?\n"
            "- Would a differential count (neutrophils, lymphocytes) help identify the cause?\n"
            "- Are any of my current medications contributing to this result?"
        ),
    },
    {
        "test_name": "Platelet Count",
        "category": "Complete Blood Count",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/platelet-tests/",
        "content": (
            "What the Test Measures:\n"
            "Platelets (thrombocytes) are small, disc-shaped blood cell fragments essential for normal blood clotting "
            "and wound healing by clumping together to form plugs at injury sites.\n\n"
            "What Elevated / High Values Mean:\n"
            "A high platelet count (thrombocytosis) can occur as a reactive response to acute infection, inflammation, "
            "tissue trauma, recent surgery, iron deficiency, or primary myeloproliferative disorders.\n\n"
            "What Low Values Mean:\n"
            "A low platelet count (thrombocytopenia) raises the risk of easy bruising and prolonged bleeding. It may stem "
            "from viral infections, autoimmune platelet destruction (ITP), splenic sequestration, or medications.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- Do I need to be cautious about bleeding or bruising given my platelet count?\n"
            "- Should we review my medications or over-the-counter pain relievers?\n"
            "- When should we perform a follow-up complete blood count?"
        ),
    },
    {
        "test_name": "Red Blood Cell Count (RBC)",
        "category": "Complete Blood Count",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/red-blood-cell-rbc-count/",
        "content": (
            "What the Test Measures:\n"
            "The RBC count measures the total number of circulating oxygen-carrying erythrocytes in a cubic millimeter of blood.\n\n"
            "What Elevated / High Values Mean:\n"
            "Elevated RBC counts (erythrocytosis) are seen in chronic hypoxia, sleep apnea, smoking, dehydration, "
            "or primary erythrocytosis (polycythemia vera).\n\n"
            "What Low Values Mean:\n"
            "Low RBC counts indicate anemia resulting from blood loss, nutritional deficiencies, hemolysis, or reduced "
            "erythropoietin production in renal disease.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- Does my RBC level align with my hemoglobin and hematocrit results?\n"
            "- Are there dietary or lifestyle factors impacting my red blood cell production?"
        ),
    },
    {
        "test_name": "Hematocrit",
        "category": "Complete Blood Count",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/hematocrit-test/",
        "content": (
            "What the Test Measures:\n"
            "Hematocrit (Hct) represents the proportion of total blood volume that consists of packed red blood cells, "
            "expressed as a percentage.\n\n"
            "What Elevated / High Values Mean:\n"
            "Elevated hematocrit often reflects hemoconcentration due to dehydration, but can also signify chronic hypoxia "
            "or polycythemia.\n\n"
            "What Low Values Mean:\n"
            "A low hematocrit is a primary hallmark of anemia or recent fluid overload.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- Was my hydration status a factor in this hematocrit reading?\n"
            "- How does this compare with previous blood counts?"
        ),
    },
    {
        "test_name": "Mean Corpuscular Volume (MCV)",
        "category": "Complete Blood Count",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/mcv-mean-corpuscular-volume/",
        "content": (
            "What the Test Measures:\n"
            "MCV measures the average physical size of your red blood cells, categorizing anemias into microcytic, "
            "normocytic, or macrocytic.\n\n"
            "What Elevated / High Values Mean:\n"
            "High MCV (macrocytosis) indicates enlarged red blood cells, commonly caused by Vitamin B12 deficiency, "
            "folate deficiency, liver dysfunction, excessive alcohol consumption, or thyroid disorders.\n\n"
            "What Low Values Mean:\n"
            "Low MCV (microcytosis) indicates smaller-than-normal red cells, most typically due to iron deficiency anemia "
            "or thalassemia trait.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- Does my cell size point toward iron deficiency or vitamin B12/folate deficiency?\n"
            "- Should we run a ferritin or hemoglobin electrophoresis panel?"
        ),
    },
    {
        "test_name": "Erythrocyte Sedimentation Rate (ESR)",
        "category": "Inflammatory Markers",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/erythrocyte-sedimentation-rate-esr/",
        "content": (
            "What the Test Measures:\n"
            "ESR is a general, non-specific test indicating the presence of systemic inflammation in the body. It measures "
            "how fast red blood cells settle to the bottom of a test tube over one hour.\n\n"
            "What Elevated / High Values Mean:\n"
            "An elevated ESR suggests active systemic inflammation, infection, autoimmune disorders (e.g. polymyalgia rheumatica, "
            "lupus, rheumatoid arthritis), inflammatory bowel disease, or tissue injury.\n\n"
            "What Low Values Mean:\n"
            "A very low ESR is typically normal, but can sometimes be observed in polycythemia, extreme leukocytosis, "
            "or sickle cell disease.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- What specific inflammatory or infectious process might be raising my sedimentation rate?\n"
            "- Would a C-Reactive Protein (CRP) test provide complementary information?"
        ),
    },
    {
        "test_name": "C-Reactive Protein (CRP)",
        "category": "Inflammatory Markers",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/c-reactive-protein-crp-test/",
        "content": (
            "What the Test Measures:\n"
            "C-reactive protein is an acute-phase reactant synthesized by the liver in response to inflammatory cytokines.\n\n"
            "What Elevated / High Values Mean:\n"
            "High CRP indicates acute or chronic inflammation. Markedly high levels (>10 mg/L) often point toward severe "
            "bacterial infections, major physical trauma, or acute flare-ups of chronic inflammatory conditions.\n\n"
            "What Low Values Mean:\n"
            "Low or undetectable CRP is normal and indicates an absence of significant systemic inflammation.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- Does this CRP elevation correlate with recent illness or symptoms?\n"
            "- Does this reflect cardiovascular risk or an inflammatory flare?"
        ),
    },

    # --------------------------------------------------------------------------
    # Lipid Panel (Cardiovascular Risk)
    # --------------------------------------------------------------------------
    {
        "test_name": "Total Cholesterol",
        "category": "Lipid Profile",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/cholesterol.html",
        "content": (
            "What the Test Measures:\n"
            "Total cholesterol quantifies the cumulative amount of cholesterol in your bloodstream, comprising HDL, "
            "LDL, and roughly 20% of triglycerides.\n\n"
            "What Elevated / High Values Mean:\n"
            "High total cholesterol (>200 mg/dL) is a recognized risk factor for atherosclerosis, coronary artery disease, "
            "and cerebrovascular events. Causes include high-saturated-fat diets, sedentary lifestyle, genetic familial "
            "hypercholesterolemia, and hypothyroidism.\n\n"
            "What Low Values Mean:\n"
            "Very low total cholesterol (<120 mg/dL) can occasionally be seen in malabsorption, severe liver disease, "
            "malnutrition, or hyperthyroidism.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- What is my overall 10-year cardiovascular risk score based on this lipid profile?\n"
            "- Are dietary and lifestyle changes sufficient, or should we discuss medical risk management?"
        ),
    },
    {
        "test_name": "HDL Cholesterol",
        "category": "Lipid Profile",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/hdlcholesterol.html",
        "content": (
            "What the Test Measures:\n"
            "High-Density Lipoprotein (HDL) is often called 'good cholesterol' because it transports excess cholesterol "
            "from peripheral tissues and arterial walls back to the liver for excretion.\n\n"
            "What Elevated / High Values Mean:\n"
            "High HDL levels (>50 mg/dL in females, >40 mg/dL in males) are generally protective against atherosclerotic "
            "cardiovascular disease.\n\n"
            "What Low Values Mean:\n"
            "Low HDL levels increase cardiovascular risk. Factors lowering HDL include cigarette smoking, metabolic syndrome, "
            "physical inactivity, obesity, and insulin resistance.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- How can I safely raise my protective HDL levels through exercise and nutrition?\n"
            "- What is my Total Cholesterol to HDL ratio?"
        ),
    },
    {
        "test_name": "LDL Cholesterol",
        "category": "Lipid Profile",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/ldlcholesterol.html",
        "content": (
            "What the Test Measures:\n"
            "Low-Density Lipoprotein (LDL) is commonly termed 'bad cholesterol' because it deposits cholesterol into arterial "
            "walls, forming atherosclerotic plaques.\n\n"
            "What Elevated / High Values Mean:\n"
            "Elevated LDL is a major causative factor in coronary heart disease, myocardial infarction, and stroke. "
            "Target thresholds depend on individual baseline cardiovascular risk profiles.\n\n"
            "What Low Values Mean:\n"
            "Low LDL is desirable for cardiovascular protection, though extremely low levels warrant clinical correlation "
            "for malabsorption or nutritional deficiencies.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- What is my personal target LDL goal based on my overall health history?\n"
            "- Should we consider additional testing such as ApoB or Lp(a)?"
        ),
    },
    {
        "test_name": "Triglycerides",
        "category": "Lipid Profile",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/triglycerides.html",
        "content": (
            "What the Test Measures:\n"
            "Triglycerides are the predominant form of dietary fat stored in adipose tissue and circulated for cellular energy.\n\n"
            "What Elevated / High Values Mean:\n"
            "High triglycerides (>150 mg/dL) are strongly linked to metabolic syndrome, insulin resistance, type 2 diabetes, "
            "alcohol excess, and cardiovascular disease. Severely high levels (>500 mg/dL) carry an increased risk of acute pancreatitis.\n\n"
            "What Low Values Mean:\n"
            "Low triglycerides can occur in malnutrition, very low-fat diets, or hyperthyroidism.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- How much do my dietary carbohydrates and sugar intake influence my triglyceride count?\n"
            "- Was my fasting interval sufficient before this blood draw?"
        ),
    },

    # --------------------------------------------------------------------------
    # Thyroid Function
    # --------------------------------------------------------------------------
    {
        "test_name": "TSH (Thyroid Stimulating Hormone)",
        "category": "Thyroid Function",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/tsh-thyroid-stimulating-hormone-test/",
        "content": (
            "What the Test Measures:\n"
            "TSH is produced by the anterior pituitary gland to regulate the thyroid gland's production of thyroxine (T4) "
            "and triiodothyronine (T3) through a sensitive negative feedback loop.\n\n"
            "What Elevated / High Values Mean:\n"
            "An elevated TSH typically indicates primary hypothyroidism (underactive thyroid), where the pituitary releases "
            "more TSH to stimulate an underperforming thyroid. Symptoms may include fatigue, weight gain, constipation, "
            "and cold sensitivity.\n\n"
            "What Low Values Mean:\n"
            "A low TSH usually signifies hyperthyroidism (overactive thyroid), where excessive circulating thyroid hormones "
            "suppress pituitary TSH secretion. Symptoms may include rapid heart rate, unintended weight loss, and tremors.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- Does my TSH result suggest an underactive or overactive thyroid state?\n"
            "- Should we check Free T4 and anti-TPO thyroid antibodies?\n"
            "- Do any supplements (such as biotin) interfere with my TSH assay?"
        ),
    },
    {
        "test_name": "Free T4 (Thyroxine)",
        "category": "Thyroid Function",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/thyroxine-t4-test/",
        "content": (
            "What the Test Measures:\n"
            "Free T4 measures the unbound, metabolically active form of thyroxine circulating in your blood, unaffected by "
            "changes in carrier protein concentrations.\n\n"
            "What Elevated / High Values Mean:\n"
            "High Free T4 indicates hyperthyroidism (such as Graves' disease, toxic multinodular goiter, or thyroiditis).\n\n"
            "What Low Values Mean:\n"
            "Low Free T4 indicates clinical hypothyroidism when accompanied by high TSH, or central hypothyroidism if TSH is normal or low.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- How does my Free T4 correlate with my TSH level?\n"
            "- Does this result explain symptoms like fatigue, heart palpitations, or weight changes?"
        ),
    },
    {
        "test_name": "Total T3 (Triiodothyronine)",
        "category": "Thyroid Function",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/triiodothyronine-t3-tests/",
        "content": (
            "What the Test Measures:\n"
            "Total T3 measures both bound and free forms of triiodothyronine, the most biologically potent thyroid hormone.\n\n"
            "What Elevated / High Values Mean:\n"
            "Elevated T3 is frequently seen in hyperthyroidism and T3 thyrotoxicosis.\n\n"
            "What Low Values Mean:\n"
            "Low T3 may indicate non-thyroidal systemic illness (euthyroid sick syndrome) or severe hypothyroidism.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- Is a Total T3 or Free T3 test more informative for my clinical situation?"
        ),
    },

    # --------------------------------------------------------------------------
    # Liver Function Panel (Hepatic)
    # --------------------------------------------------------------------------
    {
        "test_name": "Bilirubin (Total and Direct)",
        "category": "Liver Function",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/bilirubin-blood-test/",
        "content": (
            "What the Test Measures:\n"
            "Bilirubin is an orange-yellow pigment produced by the normal breakdown of hemoglobin in aged red blood cells. "
            "The liver processes and excretes bilirubin through bile ducts into the intestines.\n\n"
            "What Elevated / High Values Mean:\n"
            "Elevated bilirubin causes jaundice (yellowing of eyes and skin). Causes of unconjugated (indirect) hyperbilirubinemia "
            "include hemolysis and Gilbert's syndrome. Conjugated (direct) hyperbilirubinemia indicates biliary obstruction "
            "(gallstones, strictures) or hepatocellular liver damage (hepatitis, cirrhosis).\n\n"
            "What Low Values Mean:\n"
            "Low bilirubin is generally of no clinical significance.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- Is the elevated bilirubin predominantly conjugated (direct) or unconjugated?\n"
            "- Could Gilbert's syndrome or a biliary tract issue explain this reading?"
        ),
    },
    {
        "test_name": "SGOT / AST (Aspartate Aminotransferase)",
        "category": "Liver Function",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/ast-test/",
        "content": (
            "What the Test Measures:\n"
            "AST is an enzyme found in high concentrations in hepatocytes, cardiac myocytes, and skeletal muscle tissue. "
            "It leaks into the bloodstream when these cells sustain cellular injury.\n\n"
            "What Elevated / High Values Mean:\n"
            "Elevated AST indicates liver inflammation (viral hepatitis, fatty liver, alcoholic liver disease), drug-induced "
            "hepatotoxicity, or strenuous physical exertion and muscle damage.\n\n"
            "What Low Values Mean:\n"
            "Low AST is normal and healthy.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- How does my AST compare to my ALT level (AST/ALT ratio)?\n"
            "- Could any prescription drugs, herbal remedies, or alcohol be contributing?"
        ),
    },
    {
        "test_name": "SGPT / ALT (Alanine Aminotransferase)",
        "category": "Liver Function",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/alt-blood-test/",
        "content": (
            "What the Test Measures:\n"
            "ALT is an intracellular enzyme found almost exclusively in liver cells, making it a highly specific biomarker "
            "for hepatocellular injury.\n\n"
            "What Elevated / High Values Mean:\n"
            "Elevated ALT signifies liver cell injury. Prominent causes include non-alcoholic fatty liver disease (NAFLD), "
            "viral hepatitis (A, B, C), medications (e.g. statins, acetaminophen), or autoimmune hepatitis.\n\n"
            "What Low Values Mean:\n"
            "Low ALT is considered normal and indicates no active liver injury.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- What is the primary suspect for my elevated ALT (fatty liver, medications, viral)?\n"
            "- Would a liver ultrasound or viral hepatitis screen be indicated?"
        ),
    },
    {
        "test_name": "Alkaline Phosphatase (ALP)",
        "category": "Liver Function",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/alkaline-phosphatase-test/",
        "content": (
            "What the Test Measures:\n"
            "Alkaline phosphatase is an enzyme found particularly in the cells lining bile ducts in the liver and in active bone tissue.\n\n"
            "What Elevated / High Values Mean:\n"
            "High ALP occurs in biliary obstruction (cholestasis, gallstones), bone disorders (Paget's disease, healing fractures, "
            "bone metastases), or during normal pregnancy and childhood growth spurts.\n\n"
            "What Low Values Mean:\n"
            "Low ALP is uncommon but may occur in severe zinc deficiency, malnutrition, or hypophosphatasia.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- Does my elevated ALP originate from liver/biliary pathways or bone metabolism?\n"
            "- Should we run a GGT test to differentiate between liver and bone origin?"
        ),
    },
    {
        "test_name": "Serum Albumin",
        "category": "Liver Function",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/albumin-blood-test/",
        "content": (
            "What the Test Measures:\n"
            "Albumin is the most abundant circulating plasma protein produced by the liver, responsible for maintaining "
            "colloid oncotic pressure and transporting hormones and medications.\n\n"
            "What Elevated / High Values Mean:\n"
            "Elevated albumin is almost exclusively caused by acute hemoconcentration and dehydration.\n\n"
            "What Low Values Mean:\n"
            "Low albumin (hypoalbuminemia) indicates chronic liver failure (reduced synthesis), nephrotic syndrome (urinary loss), "
            "severe malnutrition, or acute systemic inflammatory states.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- Does my low albumin indicate a synthetic liver issue or protein loss through the kidneys?\n"
            "- Do I have fluid retention or edema related to this result?"
        ),
    },

    # --------------------------------------------------------------------------
    # Kidney Function Panel (Renal)
    # --------------------------------------------------------------------------
    {
        "test_name": "Serum Creatinine",
        "category": "Kidney Function",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/creatinine-test/",
        "content": (
            "What the Test Measures:\n"
            "Creatinine is a chemical metabolic waste product created by normal muscle contraction and breakdown. Healthy "
            "kidneys continuously filter almost all creatinine out of the blood into urine.\n\n"
            "What Elevated / High Values Mean:\n"
            "Elevated creatinine indicates impaired renal filtration capacity. Causes include acute kidney injury (from dehydration, "
            "nephrotoxic medications like NSAIDs), chronic kidney disease (hypertension, diabetes), urinary tract obstruction, "
            "or very high dietary protein/creatine intake.\n\n"
            "What Low Values Mean:\n"
            "Low creatinine is seen in individuals with low muscle mass, muscular dystrophy, or severe malnutrition.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- What does my creatinine level indicate about my overall kidney function?\n"
            "- What is my calculated estimated glomerular filtration rate (eGFR)?\n"
            "- Are any of my medications affecting my kidneys?"
        ),
    },
    {
        "test_name": "Blood Urea Nitrogen (BUN)",
        "category": "Kidney Function",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/bun-blood-urea-nitrogen-test/",
        "content": (
            "What the Test Measures:\n"
            "BUN measures the amount of nitrogen in your blood that comes from the breakdown of dietary proteins in the liver.\n\n"
            "What Elevated / High Values Mean:\n"
            "Elevated BUN occurs in kidney disease, severe dehydration, congestive heart failure, gastrointestinal bleeding, "
            "or very high protein consumption.\n\n"
            "What Low Values Mean:\n"
            "Low BUN can be seen in severe liver disease, malnutrition, low-protein diets, or fluid overload.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- What is my BUN-to-creatinine ratio, and does it suggest dehydration or kidney parenchymal injury?\n"
            "- Do I need to modify my fluid or protein intake?"
        ),
    },
    {
        "test_name": "Uric Acid",
        "category": "Kidney Function",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/uric-acid-test/",
        "content": (
            "What the Test Measures:\n"
            "Uric acid is a waste byproduct formed when the body metabolizes purines, organic compounds found in bodily cells "
            "and foods like red meat, organ meats, seafood, and alcohol.\n\n"
            "What Elevated / High Values Mean:\n"
            "High uric acid (hyperuricemia) can crystallize in joints causing acute gouty arthritis, or form uric acid kidney stones. "
            "It can be caused by genetic predisposition, renal impairment, alcohol use, or metabolic syndrome.\n\n"
            "What Low Values Mean:\n"
            "Low uric acid is relatively uncommon and generally benign.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- Does my uric acid level place me at risk for gout or kidney stones?\n"
            "- What dietary adjustments (purine reduction, hydration) do you recommend?"
        ),
    },
    {
        "test_name": "eGFR (Estimated Glomerular Filtration Rate)",
        "category": "Kidney Function",
        "source_name": "National Kidney Foundation (NKF)",
        "source_url": "https://www.kidney.org/atoz/content/gfr",
        "content": (
            "What the Test Measures:\n"
            "eGFR is the primary mathematical indicator of renal function, calculated from serum creatinine, age, and sex to "
            "estimate milliliters of blood filtered by the glomeruli per minute.\n\n"
            "What Normal / Adequate Values Mean:\n"
            "An eGFR of 60 or higher is generally considered in the normal or adequate range for adults.\n\n"
            "What Reduced / Low Values Mean:\n"
            "An eGFR below 60 for three months or longer indicates chronic kidney disease. A sudden decrease suggests acute kidney injury.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- What stage of kidney function does my eGFR correspond to?\n"
            "- What blood pressure and glycemic targets should I maintain to protect my kidneys?"
        ),
    },

    # --------------------------------------------------------------------------
    # Diabetes & Glycemic Control
    # --------------------------------------------------------------------------
    {
        "test_name": "Fasting Blood Glucose",
        "category": "Diabetes & Metabolism",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/blood-glucose-test/",
        "content": (
            "What the Test Measures:\n"
            "Measures circulating blood sugar concentration after an overnight fast of at least 8 to 12 hours.\n\n"
            "What Elevated / High Values Mean:\n"
            "Fasting glucose between 100–125 mg/dL indicates impaired fasting glucose (prediabetes). Levels ≥126 mg/dL on "
            "repeat testing indicate diabetes mellitus. Acute stress, steroids, and pancreatitis can also elevate glucose.\n\n"
            "What Low Values Mean:\n"
            "Low blood glucose (hypoglycemia, <70 mg/dL) causes dizziness, shakiness, and diaphoresis, commonly triggered "
            "by diabetic medications, skipped meals, or insulinoma.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- Does my fasting glucose reading suggest prediabetes or diabetes?\n"
            "- Should we confirm with an HbA1c test?"
        ),
    },
    {
        "test_name": "HbA1c (Glycated Hemoglobin)",
        "category": "Diabetes & Metabolism",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/hemoglobin-a1c-hba1c-test/",
        "content": (
            "What the Test Measures:\n"
            "HbA1c reflects your average blood sugar levels over the preceding 2 to 3 months by measuring the percentage "
            "of hemoglobin molecules in red blood cells coated with glucose.\n\n"
            "What Diagnostic Thresholds Mean:\n"
            "Normal: Below 5.7%.\n"
            "Prediabetes: 5.7% to 6.4%.\n"
            "Diabetes: 6.5% or higher on two separate occasions.\n"
            "In diagnosed diabetics, individual target goals (often <7.0%) are customized with a physician.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- Does my HbA1c indicate prediabetes or diabetes?\n"
            "- What individualized target HbA1c should I aim for over the next 3 months?\n"
            "- How often should I recheck my HbA1c?"
        ),
    },

    # --------------------------------------------------------------------------
    # Vitamins & Minerals
    # --------------------------------------------------------------------------
    {
        "test_name": "Vitamin D (25-Hydroxyvitamin D)",
        "category": "Vitamins & Minerals",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/vitamin-d-test/",
        "content": (
            "What the Test Measures:\n"
            "25-hydroxyvitamin D is the chief circulating form of vitamin D, essential for calcium absorption, bone mineralization, "
            "and immune modulation.\n\n"
            "What Low Values Mean:\n"
            "Deficiency (<20 ng/mL) or insufficiency (20–30 ng/mL) can cause osteopenia, osteoporosis, rickets, muscle aches, "
            "and impaired immune function. Risk factors include minimal sunlight exposure, dark skin pigmentation, malabsorption, and obesity.\n\n"
            "What Elevated / High Values Mean:\n"
            "High levels (>100 ng/mL) usually occur from excessive high-dose supplementation and can lead to hypercalcemia.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- What dosage and duration of vitamin D supplementation do you recommend for my level?\n"
            "- Should I also check my calcium and parathyroid hormone (PTH) levels?"
        ),
    },
    {
        "test_name": "Vitamin B12 (Cobalamin)",
        "category": "Vitamins & Minerals",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/vitamin-b12-test/",
        "content": (
            "What the Test Measures:\n"
            "Vitamin B12 is an essential water-soluble vitamin necessary for red blood cell production, cellular DNA synthesis, "
            "and neurological nerve myelin sheath preservation.\n\n"
            "What Low Values Mean:\n"
            "Low B12 causes megaloblastic anemia and progressive peripheral neuropathy (tingling, numbness, memory impairment). "
            "Common in strict vegetarians/vegans, pernicious anemia, gastric bypass surgery, and long-term metformin or PPI use.\n\n"
            "What Elevated / High Values Mean:\n"
            "High B12 can occur from supplementation or occasionally indicates liver disease or myeloproliferative disorders.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- Could my diet or medications (like metformin or antacids) be contributing to low B12?\n"
            "- Would oral supplements or B12 injections be more effective for me?"
        ),
    },
    {
        "test_name": "Serum Calcium",
        "category": "Electrolytes & Minerals",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/calcium-blood-test/",
        "content": (
            "What the Test Measures:\n"
            "Measures calcium in blood plasma, indispensable for bone structural integrity, cardiac contractility, nerve transmission, "
            "and coagulation cascades.\n\n"
            "What Elevated / High Values Mean:\n"
            "High calcium (hypercalcemia) is most commonly caused by primary hyperparathyroidism or malignancy. Symptoms include "
            "nephrolithiasis (kidney stones), bone pain, abdominal pain, and confusion.\n\n"
            "What Low Values Mean:\n"
            "Low calcium (hypocalcemia) causes neuromuscular excitability, muscle spasms, tetany, and tingling around the mouth. "
            "Causes include hypoparathyroidism, severe vitamin D deficiency, renal failure, or low serum albumin.\n\n"
            "Questions to Ask Your Doctor:\n"
            "- Was my calcium result corrected for my serum albumin level?\n"
            "- Should we check my parathyroid hormone (PTH) and vitamin D levels?"
        ),
    },
    {
        "test_name": "Serum Iron & Ferritin",
        "category": "Iron Studies",
        "source_name": "MedlinePlus (U.S. National Library of Medicine)",
        "source_url": "https://medlineplus.gov/lab-tests/iron-tests/",
        "content": (
            "What the Test Measures:\n"
            "Serum iron measures circulating iron bound to transferrin, while Ferritin measures the total cellular iron stores "
            "in your body.\n\n"
            "What Low Values Mean:\n"
            "Low iron and ferritin signify depleted iron stores and iron-deficiency anemia, often from menstrual loss, GI bleeding, "
            "or low dietary intake.\n\n"
            "What Elevated / High Values Mean:\n"
            "Elevated iron and ferritin can point toward hemochromatosis (iron overload), repeated blood transfusions, or chronic "
            "inflammatory conditions (where ferritin acts as an acute-phase reactant).\n\n"
            "Questions to Ask Your Doctor:\n"
            "- Do my ferritin and transferrin saturation levels confirm iron deficiency?\n"
            "- Should we investigate potential occult gastrointestinal blood loss?"
        ),
    },
]


def curate_all():
    """Write all clinical documents and companion metadata files into data/rag_sources."""
    RAG_SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Curating {len(DOCUMENTS)} clinical reference documents in {RAG_SOURCES_DIR}...")

    for doc in DOCUMENTS:
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in doc["test_name"].lower())
        txt_path = RAG_SOURCES_DIR / f"{safe_name}.txt"
        meta_path = RAG_SOURCES_DIR / f"{safe_name}.meta.json"

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(doc["content"])

        meta_dict = {
            "test_name": doc["test_name"],
            "category": doc["category"],
            "source_name": doc["source_name"],
            "source_url": doc["source_url"],
            "language": "en",
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_dict, f, indent=2)

        print(f" -> Curated: {safe_name}.txt ({len(doc['content'].split())} words)")

    print(f"Successfully curated {len(DOCUMENTS)} clinical reference documents.")


if __name__ == "__main__":
    curate_all()
