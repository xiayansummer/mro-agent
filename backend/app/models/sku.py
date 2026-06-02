from sqlalchemy import Column, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class ItemSample(Base):
    # 原 t_item_sample 在生产不存在;指向聚合视图 v_item_info(UNION 10 个商品
    # 分片 + 翻译出 brand_name/l*_category_name)。本模型目前无人查询,字段与
    # 视图列保持一致以备将来 ORM 使用。
    __tablename__ = "v_item_info"

    item_code = Column(String(50), primary_key=True)
    item_name = Column(String(500))
    brand_name = Column(String(200))
    specification = Column(String(500))
    mfg_sku = Column(String(100))
    l1_category_name = Column(String(200))
    l2_category_name = Column(String(200))
    l3_category_name = Column(String(200))
    l4_category_name = Column(String(200))
    attribute_details = Column(Text)

    def to_dict(self) -> dict:
        return {
            "item_code": self.item_code,
            "item_name": self.item_name,
            "brand_name": self.brand_name,
            "specification": self.specification,
            "mfg_sku": self.mfg_sku,
            "l1_category_name": self.l1_category_name,
            "l2_category_name": self.l2_category_name,
            "l3_category_name": self.l3_category_name,
            "l4_category_name": self.l4_category_name,
            "attribute_details": self.attribute_details,
        }
