from __future__ import absolute_import

from rest_framework import permissions
from rest_framework.serializers import ModelSerializer, ValidationError
from rest_framework.validators import UniqueValidator
from rest_framework.viewsets import ModelViewSet
from rest_framework.fields import IntegerField, UUIDField

from push_notifications.models import APNSDevice, GCMDevice
from push_notifications.fields import hex_re
from push_notifications.fields import UNSIGNED_64BIT_INT_MAX_VALUE

# Fields


class HexIntegerField(IntegerField):
	"""
	Store an integer represented as a hex string of form "0x01".
	"""

	def to_internal_value(self, data):
		# validate hex string and convert it to the unsigned
		# integer representation for internal use
		try:
			data = int(data, 16)
		except ValueError:
			raise ValidationError("Device ID is not a valid hex number")
		return super(HexIntegerField, self).to_internal_value(data)

	def to_representation(self, value):
		return value


# Serializers
class DeviceSerializerMixin(ModelSerializer):
	class Meta:
		fields = ("name", "application_id", "registration_id", "device_id", "active", "date_created")
		read_only_fields = ("date_created", )

		# See https://github.com/tomchristie/django-rest-framework/issues/1101
		extra_kwargs = {"active": {"default": True}}


class APNSDeviceSerializer(ModelSerializer):
	device_id = UUIDField(
		help_text="UDID / UIDevice.identifierForVendor() (e.g. 5ce0e9a5-5ffa-654b-cee0-1238041fb31a)",
		style={'input_type': 'text'},
		required=False
	)

	class Meta(DeviceSerializerMixin.Meta):
		model = APNSDevice

	def validate_registration_id(self, value):
		# iOS device tokens are 256-bit hexadecimal (64 characters)

		if hex_re.match(value) is None or len(value) != 64:
			raise ValidationError("Registration ID (device token) is invalid")

		return value


class GCMDeviceSerializer(ModelSerializer):
	device_id = HexIntegerField(
		help_text="ANDROID_ID / TelephonyManager.getDeviceId() (e.g: 0x01)",
		style={'input_type': 'text'},
		required=False
	)

	class Meta(DeviceSerializerMixin.Meta):
		model = GCMDevice

		extra_kwargs = {
			# Work around an issue with validating the uniqueness of
			# registration ids of up to 4k
			'registration_id': {
				'validators': [
					UniqueValidator(queryset=GCMDevice.objects.all())
				]
			}
		}

	def validate_device_id(self, value):
		# device ids are 64 bit unsigned values
		if value > UNSIGNED_64BIT_INT_MAX_VALUE:
			raise ValidationError("Device ID is out of range")
		return value


# Permissions
class IsOwner(permissions.BasePermission):
	def has_object_permission(self, request, view, obj):
		# must be the owner to view the object
		return obj.user == request.user


# Mixins
class DeviceViewSetMixin(object):
	lookup_field = "registration_id"

	def perform_create(self, serializer):
		if self.request.user.is_authenticated():
			serializer.save(user=self.request.user)
		return super(DeviceViewSetMixin, self).perform_create(serializer)


class AuthorizedMixin(object):
	permission_classes = (permissions.IsAuthenticated, IsOwner)

	def get_queryset(self):
		# filter all devices to only those belonging to the current user
		return self.queryset.filter(user=self.request.user)


# ViewSets
class APNSDeviceViewSet(DeviceViewSetMixin, ModelViewSet):
	queryset = APNSDevice.objects.all()
	serializer_class = APNSDeviceSerializer


class APNSDeviceAuthorizedViewSet(AuthorizedMixin, APNSDeviceViewSet):
	pass


class GCMDeviceViewSet(DeviceViewSetMixin, ModelViewSet):
	queryset = GCMDevice.objects.all()
	serializer_class = GCMDeviceSerializer


class GCMDeviceAuthorizedViewSet(AuthorizedMixin, GCMDeviceViewSet):
	pass
