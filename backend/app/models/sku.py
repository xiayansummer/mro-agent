from sqlalchemy import Column, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class ItemSample(Base):
    __tablename__ = "t_item_sample"

    item_code = Column(String(50), primary_key=True)
    item_name = Column(String(500))
    brand_name = Column(String(200))
    specification = Column(String(500))
    unit = Column(String(50))
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
            "unit": self.unit,
            "l1_category_name": self.l1_category_name,
            "l2_category_name": self.l2_category_name,
            "l3_category_name": self.l3_category_name,
            "l4_category_name": self.l4_category_name,
            "attribute_details": self.attribute_details,
        }
