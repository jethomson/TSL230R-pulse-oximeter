/*
  This code is based off the LUFA library and LoopBack demo code. Changes and additions
  to the original code are copyright 2013 Jonathan Thomson, jethomson.wordpress.com

  LUFA code is copyright 2009 Dean Camera (dean [at] fourwalledcubicle [dot] com)
  LoopBack demo code is copyright 2010-03-03 Opendous Inc.
    For more info visit: https://code.google.com/archive/p/micropendous/wikis/LoopBack.wiki

  This firmware enumerates as a vendor-class device meaning
  the developer must decide and code a communication scheme.
  Examples of arbitrary endpoint as well as control endpoint
  communication are given.
  Search for TODO statements for implementation hints.
  Avoid busy loops as the USB task is not preemptive and USB
  has timing contraints.  Use concurrent programming techniques.
  For example, have one function set a flag when an event occurs.
  Have another function do significant processing only if the flag is set.
  Have both functions run from main()'s for(;;) loop, which should be the
  only indefinite loop in your firmware.

  Permission to use, copy, modify, and distribute this software
  and its documentation for any purpose and without fee is hereby
  granted, provided that the above copyright notice appear in all
  copies and that both that the copyright notice and this
  permission notice and warranty disclaimer appear in supporting
  documentation, and that the name of the author not be used in
  advertising or publicity pertaining to distribution of the
  software without specific, written prior permission.

  The author disclaim all warranties with regard to this
  software, including all implied warranties of merchantability
  and fitness.  In no event shall the author be liable for any
  special, indirect or consequential damages or any damages
  whatsoever resulting from loss of use, data or profits, whether
  in an action of contract, negligence or other tortious action,
  arising out of or in connection with the use or performance of
  this software.
*/

/** \file
 *
 *  Header file for Descriptors.c.
 */

#ifndef _DESCRIPTORS_H_
#define _DESCRIPTORS_H_

	/* Includes: */
		#include <LUFA/Drivers/USB/USB.h>
		#include <avr/pgmspace.h>

	/* Global Defines */
		#define IN_EP                       1
		#define OUT_EP                      2
		#define EP_SIZE                  	64
		#define IN_EP_SIZE                  EP_SIZE
		#define OUT_EP_SIZE                 EP_SIZE

	/* Type Defines: */

		/** Type define for the device configuration descriptor structure. This must be defined in the
		 *  application code, as the configuration descriptor contains several sub-descriptors which
		 *  vary between devices, and which describe the device's usage to the host.
		 */
		typedef struct
		{
			USB_Descriptor_Configuration_Header_t Config;
			USB_Descriptor_Interface_t            Interface;
			USB_Descriptor_Endpoint_t             DataINEndpoint;
			USB_Descriptor_Endpoint_t             DataOUTEndpoint;
		} USB_Descriptor_Configuration_t;

	/* External Variables: */
		extern const USB_Descriptor_Configuration_t ConfigurationDescriptor;

	/* Macros: */
	/* Function Prototypes: */
		uint16_t CALLBACK_USB_GetDescriptor(const uint16_t wValue,
		                                    const uint8_t wIndex,
		                                    const void** const DescriptorAddress)
		                                    ATTR_WARN_UNUSED_RESULT ATTR_NON_NULL_PTR_ARG(3);

#endif
