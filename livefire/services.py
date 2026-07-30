from decimal import Decimal, ROUND_HALF_UP

ZERO = Decimal("0")
CENT = Decimal("0.01")


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def calculate(scenario):
    menu = list(scenario.menu_items.all())
    day_rows = list(scenario.days.all())
    if not day_rows:
        day_rows = [type("DefaultDay", (), {"day": "day", "traffic": scenario.traffic, "capture_rate": scenario.capture_rate, "hours": scenario.hours_per_day, "occurrences": scenario.operating_days, "max_transactions_per_hour": scenario.max_transactions_per_hour})()]
    receipt = sum((i.price * i.purchase_rate for i in menu), ZERO)
    unit_food = sum((i.food_cost * i.purchase_rate for i in menu), ZERO)
    unit_packaging = sum((i.packaging_cost * i.purchase_rate for i in menu), ZERO)
    entree_mix = sum((i.purchase_rate for i in menu if i.category == "entree"), ZERO)
    fixed = scenario.fixed_costs + scenario.operating_expenses + sum((e.amount for e in scenario.expenses.all()), ZERO)
    daily, totals = [], {k: ZERO for k in ("customers", "revenue", "food", "packaging", "waste", "labor", "card_fees", "sales_tax", "contribution")}
    for day in day_rows:
        customers = Decimal(day.traffic) * day.capture_rate
        revenue = customers * receipt
        food = customers * unit_food
        packaging = customers * unit_packaging
        waste = (food + packaging) * Decimal(str(scenario.waste_rate))
        labor_each = sum((s.daily_cost for s in scenario.staffing.all() if s.day == day.day), ZERO)
        card = revenue * Decimal(str(scenario.card_rate)) + customers * Decimal(str(scenario.card_fixed_fee))
        sales_tax = revenue * Decimal(str(scenario.sales_tax_rate)) if scenario.sales_tax_treatment == "included" else ZERO
        contribution = revenue - food - packaging - waste - labor_each - card - sales_tax
        tx_hour = customers / day.hours if day.hours else ZERO
        row = {"day": day.get_day_display() if hasattr(day, "get_day_display") else "Average day", "customers": money(customers), "receipt": money(receipt), "revenue": money(revenue), "food": money(food), "packaging": money(packaging), "waste": money(waste), "labor": money(labor_each), "card_fees": money(card), "sales_tax": money(sales_tax), "contribution": money(contribution), "transactions_per_hour": money(tx_hour), "capacity_warning": tx_hour > day.max_transactions_per_hour, "occurrences": day.occurrences}
        daily.append(row)
        for key in totals:
            totals[key] += Decimal(row[key]) * day.occurrences
    variable_per_customer = (receipt * Decimal(str(scenario.sales_tax_rate)) if scenario.sales_tax_treatment == "included" else ZERO) + unit_food + unit_packaging + (unit_food + unit_packaging) * Decimal(str(scenario.waste_rate)) + receipt * Decimal(str(scenario.card_rate)) + Decimal(str(scenario.card_fixed_fee))
    per_customer_contribution = receipt - variable_per_customer
    totals = {k: money(v) for k, v in totals.items()}
    totals["fixed"] = money(fixed)
    totals["profit"] = money(totals["contribution"] - fixed)
    totals["break_even_customers"] = money(fixed / per_customer_contribution) if per_customer_contribution > 0 else None
    return {"daily": daily, "totals": totals, "receipt": money(receipt), "entree_mix": entree_mix, "entree_mix_warning": abs(entree_mix - Decimal("1")) > Decimal(".001")}


def snapshot_data(scenario):
    result = calculate(scenario)
    result["scenario"] = scenario.name
    result["menu"] = [{"name": i.name, "category": i.get_category_display(), "price": str(i.price), "food_cost": str(i.food_cost), "packaging_cost": str(i.packaging_cost), "purchase_rate": str(i.purchase_rate), "contribution": str(i.unit_contribution)} for i in scenario.menu_items.all()]
    result["staffing"] = [{"day": s.get_day_display(), "position": s.position, "count": s.employee_count, "hours": str(s.hours), "wage": str(s.wage), "daily_cost": str(s.daily_cost)} for s in scenario.staffing.all()]
    result["expenses"] = [{"name": e.name, "amount": str(e.amount)} for e in scenario.expenses.all()]
    for row in result["daily"]:
        for key, value in row.items():
            if isinstance(value, Decimal): row[key] = str(value)
    result["totals"] = {k: str(v) if isinstance(v, Decimal) else v for k, v in result["totals"].items()}
    result["receipt"] = str(result["receipt"])
    result["entree_mix"] = str(result["entree_mix"])
    return result


def create_base_scenario(owner):
    from .models import DayAssumption, Expense, MenuItem, Scenario, StaffingLine
    scenario = Scenario.objects.create(owner=owner, name="Base", traffic=10000, capture_rate=Decimal(".10"), operating_days=20, hours_per_day=9, max_transactions_per_hour=150, sales_tax_rate=Decimal(".087"), fixed_costs=22600)
    for day, _ in DayAssumption.DAYS:
        DayAssumption.objects.create(scenario=scenario, day=day, traffic=10000, capture_rate=Decimal(".10"), hours=9, occurrences=5, max_transactions_per_hour=150)
    menu = [
        ("Salmon Platter", "entree", "26", "11", "1.25", ".30"), ("Vegetarian", "entree", "12", "4", ".50", ".10"),
        ("Tri-Tip", "entree", "16", "6", ".50", ".25"), ("Chorizo", "entree", "12", "4", ".50", ".25"), ("Kids", "entree", "7", "2", ".50", ".10"),
        ("Sides", "addon", "6", "2", "0", ".20"), ("Beverages", "addon", "4", "2", "0", ".60"),
    ]
    for name, category, price, food, packaging, rate in menu: MenuItem.objects.create(scenario=scenario, name=name, category=category, price=price, food_cost=food, packaging_cost=packaging, purchase_rate=rate)
    for day, _ in DayAssumption.DAYS:
        for position, count, hours, wage in (("Chef", 1, 7, 30), ("Prep", 2, 8, 20), ("Cashier", 2, 8, 20), ("Cashier", 1, 6.5, 20)):
            StaffingLine.objects.create(scenario=scenario, day=day, position=position, employee_count=count, hours=hours, wage=wage)
    for name, amount in (("Space lease", 4000), ("Restrooms", 5000), ("Handwashing stations", 2000), ("Picnic tables", 2000), ("Fencing", 1000), ("Refrigerated truck", 4000), ("Prep tables", 500), ("POS system", 100), ("Signage", 2000), ("Fire pit racks", 1000), ("Fire pit blocks", 1000), ("Firewood", 1000)):
        Expense.objects.create(scenario=scenario, name=name, amount=amount)
    scenario.fixed_costs = 0; scenario.save(update_fields=["fixed_costs"])
    return scenario
