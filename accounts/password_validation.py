"""Django's default password rules with Thai messages.

The rules are exactly Django's own (decided: no extra rules). Only the texts
change, because Django's Thai translation leaves these messages in English.
"""

from django.contrib.auth import password_validation as django_rules


class UserAttributeSimilarityValidator(django_rules.UserAttributeSimilarityValidator):
    def get_error_message(self) -> str:
        return "รหัสผ่านคล้ายกับ%(verbose_name)sมากเกินไป"

    def get_help_text(self) -> str:
        return "รหัสผ่านต้องไม่คล้ายกับชื่อผู้ใช้ ชื่อ หรือนามสกุล"


class MinimumLengthValidator(django_rules.MinimumLengthValidator):
    def get_error_message(self) -> str:
        return f"รหัสผ่านสั้นเกินไป ต้องมีอย่างน้อย {self.min_length} ตัวอักษร"

    def get_help_text(self) -> str:
        return f"รหัสผ่านต้องมีอย่างน้อย {self.min_length} ตัวอักษร"


class CommonPasswordValidator(django_rules.CommonPasswordValidator):
    def get_error_message(self) -> str:
        return "รหัสผ่านนี้ถูกใช้บ่อยเกินไป เดาได้ง่าย"

    def get_help_text(self) -> str:
        return "รหัสผ่านต้องไม่ใช่รหัสที่คนใช้กันบ่อย"


class NumericPasswordValidator(django_rules.NumericPasswordValidator):
    def get_error_message(self) -> str:
        return "รหัสผ่านต้องไม่เป็นตัวเลขทั้งหมด"

    def get_help_text(self) -> str:
        return "รหัสผ่านต้องไม่เป็นตัวเลขทั้งหมด"
