from . import db
from .main.utils import link, url_for
from sqlalchemy.dialects.postgresql import JSON


class Framework(db.Model):
    __tablename__ = 'frameworks'

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(255), nullable=False)

    expired = db.Column(db.Boolean, index=False, unique=False,
                        nullable=False)


class Supplier(db.Model):
    __tablename__ = 'suppliers'

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.BigInteger,
                            index=True, unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)

    def serialize(self):
        links = [
            link(
                "self",
                url_for(".get_supplier", supplier_id=self.supplier_id)
            )
        ]

        return {
            'id': self.supplier_id,
            'name': self.name,
            'links': links
        }


class Service(db.Model):
    __tablename__ = 'services'

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.String,
                           index=True, unique=True, nullable=False)
    supplier_id = db.Column(db.BigInteger,
                            db.ForeignKey('suppliers.supplier_id'),
                            index=True, unique=False, nullable=False)
    created_at = db.Column(db.DateTime, index=False, unique=False,
                           nullable=False)
    updated_at = db.Column(db.DateTime, index=False, unique=False,
                           nullable=False)
    updated_by = db.Column(db.String, index=False, unique=False,
                           nullable=False)
    updated_reason = db.Column(db.String, index=False, unique=False,
                               nullable=False)
    data = db.Column(JSON)

    framework_id = db.Column(db.BigInteger,
                             db.ForeignKey('frameworks.id'),
                             index=True, unique=False, nullable=False)

    status = db.Column(db.String, index=False, unique=False, nullable=False)

    supplier = db.relationship(Supplier, lazy='joined', innerjoin=True)

    framework = db.relationship(Framework, lazy='joined', innerjoin=True)

    def serialize(self):
        """
        Pretty much a direct translation of the old `jsonify_service` function
        :return: dictionary representation of a service
        """

        data = dict(self.data.items())

        data.update({
            'id': self.service_id,
            'supplierId': self.supplier.supplier_id,
            'supplierName': self.supplier.name,
        })

        data['links'] = [
            link(
                "self",
                url_for(".get_service", service_id=data['id'])
            )
        ]

        return data


class ArchivedService(db.Model):
    __tablename__ = 'archived_services'

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.String,
                           index=True, unique=False, nullable=False)
    supplier_id = db.Column(db.BigInteger,
                            db.ForeignKey('suppliers.supplier_id'),
                            index=True, unique=False, nullable=False)
    created_at = db.Column(db.DateTime, index=False, unique=False,
                           nullable=False)
    updated_at = db.Column(db.DateTime, index=False, unique=False,
                           nullable=False)
    updated_by = db.Column(db.String, index=False, unique=False,
                           nullable=False)
    updated_reason = db.Column(db.String, index=False, unique=False,
                               nullable=False)
    data = db.Column(JSON)

    framework_id = db.Column(db.BigInteger,
                             db.ForeignKey('frameworks.id'),
                             index=True, unique=False, nullable=False)

    status = db.Column(db.String, index=False, unique=False, nullable=False)

    supplier = db.relationship(Supplier, lazy='joined', innerjoin=True)

    framework = db.relationship(Framework, lazy='joined', innerjoin=True)

    @staticmethod
    def from_service(service):
        return ArchivedService(
            framework_id=service.framework_id,
            service_id=service.service_id,
            supplier_id=service.supplier_id,
            created_at=service.created_at,
            updated_at=service.updated_at,
            updated_by=service.updated_by,
            updated_reason=service.updated_reason,
            data=service.data,
            status=service.status
        )

    def serialize(self):
        """
        Pretty much a direct translation of the old `jsonify_service` function
        :return: dictionary representation of a service
        """

        data = dict(self.data.items())

        data.update({
            'id': self.service_id,
            'supplierId': self.supplier.supplier_id,
            'supplierName': self.supplier.name,
        })

        data['links'] = [
            link(
                "self",
                url_for(".get_service", service_id=data['id'])
            )
        ]

        return data
