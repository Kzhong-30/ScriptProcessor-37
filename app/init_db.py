import random
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.database import Base, engine, SessionLocal
from app.models import User, Product, Event, EventType
from app.config import settings


CATEGORIES = ["手机数码", "家用电器", "服装鞋包", "美妆个护", "食品生鲜", "图书文娱", "运动户外", "母婴玩具"]
BRANDS = {
    "手机数码": ["Apple", "华为", "小米", "三星", "OPPO", "vivo"],
    "家用电器": ["美的", "海尔", "格力", "西门子", "LG", "飞利浦"],
    "服装鞋包": ["Nike", "Adidas", "优衣库", "ZARA", "李宁", "安踏"],
    "美妆个护": ["兰蔻", "雅诗兰黛", "SK-II", "资生堂", "欧莱雅", "完美日记"],
    "食品生鲜": ["三只松鼠", "良品铺子", "百草味", "褚橙", "伊利", "蒙牛"],
    "图书文娱": ["当当", "京东图书", "Kindle", "机械工业出版社", "中信出版社", "人民邮电出版社"],
    "运动户外": ["北面", "哥伦比亚", "始祖鸟", "迪卡侬", "探路者", "骆驼"],
    "母婴玩具": ["乐高", "费雪", "美赞臣", "惠氏", "帮宝适", "巴拉巴拉"],
}
TAGS_POOL = [
    "新品", "热销", "限量", "折扣", "包邮", "明星同款", "国货",
    "高端", "入门", "学生党", "商务", "休闲", "运动", "送礼",
    "便携", "智能", "无线", "蓝牙", "高清", "轻薄", "大容量"
]
ADJECTIVES = ["旗舰", "高端", "经典", "时尚", "专业", "轻奢", "超值", "人气", "爆款", "精选"]


def generate_product_name(category: str, brand: str) -> str:
    adj = random.choice(ADJECTIVES)
    if category == "手机数码":
        suffix = random.choice(["手机", "笔记本电脑", "平板电脑", "耳机", "智能手表", "相机"])
    elif category == "家用电器":
        suffix = random.choice(["冰箱", "洗衣机", "空调", "电视", "吸尘器", "电饭煲"])
    elif category == "服装鞋包":
        suffix = random.choice(["T恤", "运动鞋", "牛仔裤", "外套", "背包", "连衣裙"])
    elif category == "美妆个护":
        suffix = random.choice(["面霜", "精华液", "口红", "面膜", "洗发水", "香水"])
    elif category == "食品生鲜":
        suffix = random.choice(["坚果礼盒", "零食大礼包", "牛奶", "巧克力", "水果礼盒", "茶叶"])
    elif category == "图书文娱":
        suffix = random.choice(["畅销小说", "技术图书", "漫画", "文具套装", "电子书阅读器", "唱片"])
    elif category == "运动户外":
        suffix = random.choice(["登山鞋", "帐篷", "瑜伽垫", "运动套装", "骑行装备", "钓鱼竿"])
    else:
        suffix = random.choice(["积木", "毛绒玩具", "婴儿奶粉", "纸尿裤", "儿童服饰", "益智玩具"])
    return f"{brand} {adj}{suffix}"


def generate_tags() -> str:
    n = random.randint(2, 5)
    selected = random.sample(TAGS_POOL, n)
    return ",".join(selected)


def init_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("数据库表已创建")

    db = SessionLocal()
    try:
        users = []
        for i in range(1, 51):
            user = User(
                username=f"user_{i:03d}",
                email=f"user_{i:03d}@example.com"
            )
            users.append(user)
        db.add_all(users)
        db.flush()
        print(f"已创建 {len(users)} 个用户")

        products = []
        for i in range(1, 201):
            category = random.choice(CATEGORIES)
            brand = random.choice(BRANDS[category])
            days_ago = random.randint(0, 90)
            created_at = datetime.now() - timedelta(days=days_ago)
            product = Product(
                name=generate_product_name(category, brand),
                description=f"这是一款来自{brand}的优质商品，品质保证，售后无忧。",
                price=round(random.uniform(9.9, 9999.9), 2),
                category=category,
                brand=brand,
                tags=generate_tags(),
                created_at=created_at
            )
            products.append(product)
        db.add_all(products)
        db.flush()
        print(f"已创建 {len(products)} 个商品")

        events = []
        event_types = list(EventType)
        now = datetime.now()
        for user_id in range(1, 51):
            n_events = random.randint(15, 80)
            interacted_products = set()
            for _ in range(n_events):
                product_id = random.randint(1, 200)
                if product_id in interacted_products and random.random() > 0.3:
                    continue
                interacted_products.add(product_id)
                event_type = random.choices(
                    event_types,
                    weights=[40, 25, 15, 8, 12],
                    k=1
                )[0]
                hours_ago = random.randint(0, 24 * settings.TRENDING_WINDOW_DAYS)
                timestamp = now - timedelta(hours=hours_ago)
                events.append(Event(
                    user_id=user_id,
                    product_id=product_id,
                    event_type=event_type,
                    timestamp=timestamp,
                    session_id=f"sess_{random.randint(1, 1000)}"
                ))
        db.add_all(events)
        db.flush()
        print(f"已创建 {len(events)} 条行为事件")

        new_user = User(username="new_user_999", email="new_user_999@example.com")
        db.add(new_user)
        db.flush()
        print("已创建冷启动测试用户 new_user_999")

        db.commit()
        print("数据初始化完成！")

    except Exception as e:
        db.rollback()
        print(f"初始化失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
