from __future__ import annotations
import argparse, copy, json, math
from pathlib import Path

TOL=1e-6

def npv(rate, cashflows):
 return sum(v/((1+rate)**i) for i,v in enumerate(cashflows))

def irr(cashflows):
 if not any(x<0 for x in cashflows) or not any(x>0 for x in cashflows): return None
 rates=[-0.99+i*(10.99/5000) for i in range(5001)]
 prev_r=rates[0]; prev=npv(prev_r,cashflows)
 for r in rates[1:]:
  cur=npv(r,cashflows)
  if cur==0: return r
  if prev*cur<0:
   lo,hi=prev_r,r
   for _ in range(100):
    mid=(lo+hi)/2; val=npv(mid,cashflows)
    if abs(val)<1e-8: return mid
    if npv(lo,cashflows)*val<=0: hi=mid
    else: lo=mid
   return (lo+hi)/2
  prev_r,prev=r,cur
 return None

def payback(cashflows, rate=0):
 cum=cashflows[0]
 if cum>=0:return 0.0
 for y in range(1,len(cashflows)):
  val=cashflows[y]/((1+rate)**y)
  old=cum; cum+=val
  if cum>=0 and val>0:return (y-1)+(-old/val)
 return None

def validate(c):
 p=c["project"]; pv=c["pv"]; st=c["storage"]; ch=c["charging"]; debt=c["debt"]
 years=int(p["projection_years"])
 if years<1 or years>40: raise ValueError("projection_years must be 1..40")
 arr=ch["demand_multiplier_by_year"]
 if not isinstance(arr,list) or len(arr)!=years: raise ValueError("demand_multiplier_by_year length must equal projection_years")
 if any(float(x)<0 for x in arr): raise ValueError("demand multipliers must be nonnegative")
 for key,val in [("pv availability",pv["availability"]),("curtailment",pv["curtailment_rate"]),("pv direct share",pv["direct_to_charging_share"]),("pv storage share",pv["to_storage_share"]),("DoD",st["depth_of_discharge"]),("RTE",st["roundtrip_efficiency"]),("storage availability",st["availability"]),("online rate",ch["online_rate"]),("average power realization",ch["average_power_realization"]),("platform fee",ch["platform_fee_rate_on_service"]),("debt ratio",debt["debt_ratio"])]:
  if float(val)<0 or float(val)>1: raise ValueError(f"{key} must be within 0..1")
 if float(pv["direct_to_charging_share"])+float(pv["to_storage_share"])>1+TOL: raise ValueError("PV allocation shares exceed 100%")
 if int(debt["tenor_years"])<1 or int(debt["tenor_years"])>years: raise ValueError("invalid debt tenor")
 if min(float(p["total_capex"]),float(pv["capacity_kw"]),float(st["capacity_kwh"]),float(ch["rated_power_total_kw"]))<0: raise ValueError("capacity and capex must be nonnegative")
 for r in c.get("replacements",[]):
  if int(r["year"])<1 or int(r["year"])>years or float(r["amount"])<0: raise ValueError("invalid replacement")
 return years

def run_case(c,factors=None,storage_enabled=True):
 factors=factors or {}
 p,pv,st,ch,oc,anc,debt=(c[k] for k in ("project","pv","storage","charging","other_costs","ancillary","debt"))
 years=int(p["projection_years"]); pv_factor=float(factors.get("pv_factor",1)); demand_factor=float(factors.get("charging_demand_factor",1)); fee_factor=float(factors.get("service_fee_factor",1)); grid_factor=float(factors.get("grid_price_factor",1))
 repl={int(x["year"]):float(x["amount"]) for x in c.get("replacements",[])}
 debt_amount=float(p["total_capex"])*float(debt["debt_ratio"]); tenor=int(debt["tenor_years"]); principal=debt_amount/tenor
 opening_debt=debt_amount; rows=[]; project_cf=[-float(p["total_capex"])]; equity_cf=[-(float(p["total_capex"])-debt_amount)]
 capacity_exceeded=False; storage_infeasible=False
 for i in range(years):
  y=i+1; growth=(1+float(oc["annual_cost_growth"]))**i
  requested=float(ch["stall_count"])*float(ch["base_daily_kwh_per_stall"])*365*float(ch["demand_multiplier_by_year"][i])*demand_factor
  cap_limit=float(ch["rated_power_total_kw"])*8760*float(ch["online_rate"])*float(ch["average_power_realization"])
  demand=min(requested,cap_limit)
  if requested>cap_limit+TOL: capacity_exceeded=True
  pv_gen=float(pv["capacity_kw"])*float(pv["equivalent_hours"])*float(pv["availability"])*(1-float(pv["curtailment_rate"]))*((1-float(pv["annual_degradation"]))**i)*pv_factor
  pv_direct=min(pv_gen*float(pv["direct_to_charging_share"]),demand)
  remaining=max(0,demand-pv_direct)
  rte=float(st["roundtrip_efficiency"])
  storage_input_target=0.0
  pv_storage_possible=0.0
  if storage_enabled and float(st["capacity_kwh"])>0:
   usable=float(st["capacity_kwh"])*((1-float(st["annual_capacity_degradation"]))**i)
   storage_input_target=usable*float(st["depth_of_discharge"])*float(st["cycles_per_year"])*float(st["availability"])
   pv_storage_possible=min(max(0,pv_gen-pv_direct),pv_gen*float(pv["to_storage_share"]),storage_input_target)
   if not bool(st["allow_grid_charging"]): storage_input_target=pv_storage_possible
  discharge=min(storage_input_target*rte,remaining)
  actual_input=discharge/rte if rte>0 else 0
  pv_to_storage=min(pv_storage_possible,actual_input)
  grid_to_storage=max(0,actual_input-pv_to_storage) if bool(st["allow_grid_charging"]) else 0
  if grid_to_storage>0 and not storage_enabled: storage_infeasible=True
  pv_export=max(0,pv_gen-pv_direct-pv_to_storage)
  grid_direct=max(0,demand-pv_direct-discharge)
  pv_error=pv_gen-pv_direct-pv_to_storage-pv_export
  st_error=discharge-(pv_to_storage+grid_to_storage)*rte
  load_error=demand-pv_direct-discharge-grid_direct
  energy_error=pv_error+st_error+load_error
  energy_rev=demand*float(ch["customer_energy_price"])
  service_rev=demand*float(ch["service_fee"])*fee_factor
  export_rev=pv_export*float(pv["export_price"])
  ancillary=float(anc["annual_revenue"]) if bool(anc["verified"]) else 0.0
  total_rev=energy_rev+service_rev+export_rev+ancillary
  grid_cost=grid_direct*float(ch["direct_grid_price"])*grid_factor+grid_to_storage*float(st["offpeak_grid_price"])*grid_factor
  platform=service_rev*float(ch["platform_fee_rate_on_service"])
  variable=demand*float(ch["variable_opex_per_kwh"])
  fixed=(float(pv["capacity_kw"])*float(pv["om_per_kw_year"])+(float(st["capacity_kwh"])*float(st["om_per_kwh_year"]) if storage_enabled else 0)+float(ch["fixed_om_year"])+float(oc["site_rent_year"])+float(oc["basic_demand_charge_year"])+float(oc["insurance_and_other_year"]))*growth
  opex=grid_cost+platform+variable+fixed
  ebitda=total_rev-opex
  depreciation=float(p["total_capex"])/int(p["depreciation_years"]) if y<=int(p["depreciation_years"]) else 0
  ebit=ebitda-depreciation; tax=max(0,ebit)*float(p["tax_rate"])
  replacement=repl.get(y,0.0); cfads=ebitda-tax-replacement; project_cf.append(cfads)
  interest=opening_debt*float(debt["annual_interest_rate"]) if y<=tenor else 0
  principal_due=principal if y<=tenor else 0
  tax_shield=min(interest,max(0,ebitda))*float(p["tax_rate"])
  equity_cash=cfads-interest-principal_due+tax_shield; equity_cf.append(equity_cash)
  debt_service=interest+principal_due; dscr=cfads/debt_service if debt_service>0 else None
  closing=max(0,opening_debt-principal_due)
  rows.append({"year":y,"requested_charging_kwh":requested,"charging_capacity_limit_kwh":cap_limit,"charging_energy_kwh":demand,"pv_generation_kwh":pv_gen,"pv_direct_kwh":pv_direct,"pv_to_storage_kwh":pv_to_storage,"pv_export_kwh":pv_export,"grid_to_storage_kwh":grid_to_storage,"storage_discharge_kwh":discharge,"storage_roundtrip_efficiency":rte,"grid_direct_kwh":grid_direct,"energy_balance_error_kwh":energy_error,"charging_energy_revenue":energy_rev,"service_fee_revenue":service_rev,"pv_export_revenue":export_rev,"ancillary_revenue":ancillary,"total_revenue":total_rev,"grid_energy_cost":grid_cost,"platform_fee":platform,"variable_opex":variable,"fixed_opex":fixed,"ebitda":ebitda,"depreciation":depreciation,"tax":tax,"replacement_capex":replacement,"cfads":cfads,"opening_debt":opening_debt,"interest":interest,"principal":principal_due,"debt_service":debt_service,"dscr":dscr,"closing_debt":closing,"equity_cashflow":equity_cash})
  opening_debt=closing
 debt_dscr=[x["dscr"] for x in rows if x["dscr"] is not None]
 llcr=npv(float(debt["annual_interest_rate"]),[0]+[x["cfads"] for x in rows[:tenor]])/debt_amount if debt_amount>0 else None
 metrics={"project_npv":npv(float(p["discount_rate"]),project_cf),"project_irr":irr(project_cf),"equity_irr":irr(equity_cf),"static_payback_years":payback(project_cf),"dynamic_payback_years":payback(project_cf,float(p["discount_rate"])),"minimum_dscr":min(debt_dscr) if debt_dscr else None,"initial_llcr":llcr,"first_debt_shortfall_year":next((x["year"] for x in rows if x["dscr"] is not None and x["dscr"]<1),None)}
 return {"rows":rows,"project_cashflows":project_cf,"equity_cashflows":equity_cf,"metrics":metrics,"case_flags":{"capacity_exceeded":capacity_exceeded,"storage_infeasible":storage_infeasible}}

def run_model(config):
 c=copy.deepcopy(config); years=validate(c); flags=[]; warnings=[]
 if not bool(c["project"].get("load_data_verified",False)): flags.append("LOAD_DATA_UNVERIFIED")
 if float(c["ancillary"].get("annual_revenue",0))>0 and not bool(c["ancillary"].get("verified",False)): flags.append("UNVERIFIED_ANCILLARY_REVENUE")
 if int(c["project"]["site_term_years"])<int(c["debt"]["tenor_years"]): flags.append("SITE_TERM_SHORTER_THAN_FINANCING")
 if years>=8 and not c.get("replacements"): flags.append("REPLACEMENT_CAPEX_MISSING")
 base=run_case(c); no_storage=run_case(c,storage_enabled=False)
 sc=c.get("scenarios",{}); p90=run_case(c,sc.get("p90",{"pv_factor":.9,"charging_demand_factor":.9}))
 scenarios={k:run_case(c,v) for k,v in sc.items() if k!="p90"}
 all_cases=[base,no_storage,p90,*scenarios.values()]
 if any(x["case_flags"]["capacity_exceeded"] for x in all_cases): flags.append("CHARGING_CAPACITY_EXCEEDED")
 if any(abs(r["energy_balance_error_kwh"])>1e-4 for case in all_cases for r in case["rows"]): flags.append("ENERGY_BALANCE_BROKEN")
 if base["metrics"]["project_npv"]<0: flags.append("BASE_PROJECT_NPV_NEGATIVE")
 if any(x["cfads"]<0 for x in base["rows"]): flags.append("NEGATIVE_CFADS_IN_BASE")
 threshold=float(c["debt"]["dscr_threshold"])
 if base["metrics"]["minimum_dscr"] is not None and base["metrics"]["minimum_dscr"]<threshold: flags.append("BASE_DSCR_BELOW_THRESHOLD")
 if p90["metrics"]["minimum_dscr"] is not None and p90["metrics"]["minimum_dscr"]<1: flags.append("P90_DSCR_BELOW_1")
 pb=base["metrics"]["static_payback_years"]
 if pb is None or pb>float(c["project"]["site_term_years"]): flags.append("PAYBACK_NOT_WITHIN_SITE_TERM")
 flags=list(dict.fromkeys(flags))
 return {"model":"solar_storage_charging_project_risk_v0.1","validation":{"errors":[],"warnings":warnings},"hard_flags":flags,"base":base,"no_storage":no_storage,"p90":p90,"scenarios":scenarios}

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("input"); ap.add_argument("--output","-o"); a=ap.parse_args()
 data=json.loads(Path(a.input).read_text()); result=run_model(data); text=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
 if a.output: Path(a.output).write_text(text)
 else: print(text)

if __name__=="__main__": main()
